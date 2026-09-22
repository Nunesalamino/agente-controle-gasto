import json
import os
import re
import time
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

bedrock = boto3.client("bedrock-runtime")
dynamodb = boto3.resource("dynamodb")
textract = boto3.client("textract")
transcribe = boto3.client("transcribe")
s3 = boto3.client("s3")

table = dynamodb.Table(os.environ.get("TABLE_NAME", "Gastos"))
BUCKET_NAME = os.environ.get("BUCKET_NAME")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
# ID do seu chat no Telegram, usado só para o resumo automático mensal
# (nos disparos normais, o próprio Telegram já informa o chat_id na mensagem)
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

MODEL_ID = "us.amazon.nova-micro-v1:0"  # inference profile (necessário p/ Nova Micro)

PROMPT_TEMPLATE = """Você é um assistente que extrai dados de gastos financeiros a partir de mensagens em português do Brasil. O texto pode ser uma mensagem informal digitada, a transcrição de um áudio, ou o texto extraído de um comprovante (print de pagamento, recibo, extrato de Pix, etc.).

Dado o texto abaixo, extraia as seguintes informações e responda APENAS com um JSON válido, sem nenhum texto antes ou depois:

{{
  "valor": <número decimal, sem símbolo de moeda>,
  "local": "<nome do estabelecimento, tipo de lugar, ou nome da pessoa em caso de Pix para pessoa física>",
  "categoria": "<uma destas: supermercado, farmacia, padaria, restaurante, transporte, lazer, saude, outros>",
  "formaPagamento": "<uma destas: credito, debito, pix, dinheiro, desconhecido>"
}}

Regras:
- Se o texto parecer um comprovante bancário (contém palavras como "Comprovante", "Valor", "Pix", "Transferência", "CPF", "ID da transação", "Destino", "Origem"), o valor do gasto é o número que está ao lado do campo "Valor" — nunca confunda com números de CPF, ID de transação, conta ou agência, que não são valores monetários.
- Se o texto não descrever nenhum gasto real (por exemplo, uma saudação, uma mensagem de teste, ou qualquer coisa sem relação com dinheiro), use "valor": null e deixe os outros campos null/"desconhecido" também.
- Se o valor não estiver claro, use null.
- Se a forma de pagamento não for mencionada, use "desconhecido".
- Escolha a categoria mais provável mesmo que não seja explícita (ex: "Droga Raia" é farmacia). Um Pix para uma pessoa física sem mais contexto pode ser categorizado como "outros".
- Não invente informações que não estão no texto.

Texto: "{texto}"
"""


# ---------------------------------------------------------------------------
# Logs estruturados
# ---------------------------------------------------------------------------

def log_evento(evento, **detalhes):
    """
    Loga um evento em formato JSON (uma linha por evento) no CloudWatch Logs.
    Isso facilita consultar depois no CloudWatch Logs Insights, por exemplo:
    "quantos gastos foram ignorados por falta de valor essa semana?"
    """
    registro = {
        "evento": evento,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **detalhes,
    }
    print(json.dumps(registro, default=str))


# ---------------------------------------------------------------------------
# Bedrock
# ---------------------------------------------------------------------------

def extrair_gasto(texto):
    """Chama o Bedrock (Nova Micro) e devolve um dict com os dados extraídos."""
    prompt = PROMPT_TEMPLATE.format(texto=texto)

    response = bedrock.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
    )

    resposta_texto = response["output"]["message"]["content"][0]["text"]
    # remove eventuais ```json ... ``` que o modelo às vezes adiciona
    resposta_limpa = re.sub(r"^```json|```$", "", resposta_texto.strip()).strip()

    return json.loads(resposta_limpa)


# ---------------------------------------------------------------------------
# Extração de texto (imagem / áudio)
# ---------------------------------------------------------------------------

def extrair_texto_imagem(key):
    """Usa o Textract para ler o texto de um comprovante que já está no S3."""
    response = textract.detect_document_text(
        Document={"S3Object": {"Bucket": BUCKET_NAME, "Name": key}}
    )
    linhas = [b["Text"] for b in response["Blocks"] if b["BlockType"] == "LINE"]
    return "\n".join(linhas)


def extrair_texto_audio(key, timeout_segundos=60):
    """
    Inicia um job do Transcribe para um áudio que já está no S3,
    e fica checando o status até terminar (abordagem síncrona,
    adequada para áudios curtos de uso pessoal).
    """
    job_name = f"transcricao-{uuid.uuid4().hex[:8]}"
    media_uri = f"s3://{BUCKET_NAME}/{key}"

    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={"MediaFileUri": media_uri},
        LanguageCode="pt-BR",
        OutputBucketName=BUCKET_NAME,
    )

    decorrido = 0
    intervalo = 3
    while decorrido < timeout_segundos:
        job = transcribe.get_transcription_job(TranscriptionJobName=job_name)
        status = job["TranscriptionJob"]["TranscriptionJobStatus"]

        if status == "COMPLETED":
            transcript_key = job["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
            # o resultado fica salvo como um arquivo JSON no próprio bucket
            nome_arquivo = transcript_key.split("/")[-1]
            obj = s3.get_object(Bucket=BUCKET_NAME, Key=nome_arquivo)
            resultado = json.loads(obj["Body"].read())
            return resultado["results"]["transcripts"][0]["transcript"]

        if status == "FAILED":
            raise RuntimeError("A transcrição do áudio falhou")

        time.sleep(intervalo)
        decorrido += intervalo

    raise TimeoutError("A transcrição demorou demais e o tempo limite foi atingido")


# ---------------------------------------------------------------------------
# Telegram: baixar arquivos e enviar respostas
# ---------------------------------------------------------------------------

def telegram_chamar(metodo, payload):
    """Faz uma chamada POST simples à API do Telegram (sem depender de libs externas)."""
    url = f"{TELEGRAM_API}/{metodo}"
    dados = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=dados, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def telegram_baixar_arquivo(file_id, destino_s3_key):
    """
    Baixa um arquivo do Telegram (foto ou áudio) a partir do file_id
    e sobe para o S3, no caminho indicado. Devolve a key usada.
    """
    info = telegram_chamar("getFile", {"file_id": file_id})
    file_path = info["result"]["file_path"]

    url_arquivo = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    with urllib.request.urlopen(url_arquivo) as resp:
        conteudo = resp.read()

    s3.put_object(Bucket=BUCKET_NAME, Key=destino_s3_key, Body=conteudo)
    return destino_s3_key


def telegram_enviar_mensagem(chat_id, texto):
    """Manda uma mensagem de texto de volta para o usuário no Telegram."""
    telegram_chamar("sendMessage", {"chat_id": chat_id, "text": texto})


# ---------------------------------------------------------------------------
# DynamoDB: gravação de gastos
# ---------------------------------------------------------------------------

def salvar_gasto(dados, texto_original, fonte="texto"):
    """Monta o item no formato da tabela Gastos e salva no DynamoDB."""
    agora = datetime.now(timezone.utc).isoformat()
    valor = dados.get("valor")

    item = {
        "PK": "USER#eu",
        "SK": f"GASTO#{agora}#{uuid.uuid4().hex[:8]}",
        "valor": Decimal(str(valor)) if valor is not None else None,
        "local": dados.get("local"),
        "categoria": dados.get("categoria"),
        "formaPagamento": dados.get("formaPagamento"),
        "textoOriginal": texto_original,
        "fonte": fonte,
    }

    table.put_item(Item=item)
    return item


def formatar_confirmacao(item):
    """Monta a mensagem de confirmação amigável mandada de volta ao usuário."""
    valor = item.get("valor")
    valor_str = f"R$ {valor:.2f}" if valor is not None else "valor não identificado"
    return (
        "Gasto registrado!\n"
        f"Valor: {valor_str}\n"
        f"Local: {item.get('local') or 'não identificado'}\n"
        f"Categoria: {item.get('categoria') or 'outros'}\n"
        f"Forma de pagamento: {item.get('formaPagamento') or 'desconhecido'}"
    )


# ---------------------------------------------------------------------------
# DynamoDB: resumo mensal
# ---------------------------------------------------------------------------

def gerar_resumo(ano_mes):
    """
    Busca todos os gastos de um mês (formato 'AAAA-MM') e agrega os totais
    por categoria e por forma de pagamento. Usa a mesma PK fixa e aproveita
    a ordenação do SK (que começa com a data) para fazer uma query eficiente,
    em vez de varrer a tabela inteira.
    """
    response = table.query(
        KeyConditionExpression=Key("PK").eq("USER#eu") & Key("SK").begins_with(f"GASTO#{ano_mes}")
    )
    itens = response["Items"]

    # Se houver muitos gastos num mês só, o DynamoDB pode paginar o resultado.
    # Isso busca as páginas seguintes até não sobrar mais nada.
    while "LastEvaluatedKey" in response:
        response = table.query(
            KeyConditionExpression=Key("PK").eq("USER#eu") & Key("SK").begins_with(f"GASTO#{ano_mes}"),
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        itens.extend(response["Items"])

    total = Decimal("0")
    por_categoria = {}
    por_pagamento = {}

    for item in itens:
        valor = item.get("valor") or Decimal("0")
        categoria = item.get("categoria") or "outros"
        pagamento = item.get("formaPagamento") or "desconhecido"

        total += valor
        por_categoria[categoria] = por_categoria.get(categoria, Decimal("0")) + valor
        por_pagamento[pagamento] = por_pagamento.get(pagamento, Decimal("0")) + valor

    return {
        "ano_mes": ano_mes,
        "quantidade": len(itens),
        "total": total,
        "por_categoria": por_categoria,
        "por_pagamento": por_pagamento,
    }


def formatar_resumo(resumo):
    """Monta a mensagem de texto do resumo mensal, mandada de volta ao usuário."""
    if resumo["quantidade"] == 0:
        return f"Nenhum gasto registrado em {resumo['ano_mes']}."

    linhas = [
        f"Resumo de {resumo['ano_mes']} ({resumo['quantidade']} gastos)",
        f"Total: R$ {resumo['total']:.2f}",
        "",
        "Por categoria:",
    ]
    for categoria, valor in sorted(resumo["por_categoria"].items(), key=lambda x: -x[1]):
        linhas.append(f"- {categoria}: R$ {valor:.2f}")

    linhas.append("")
    linhas.append("Por forma de pagamento:")
    for pagamento, valor in sorted(resumo["por_pagamento"].items(), key=lambda x: -x[1]):
        linhas.append(f"- {pagamento}: R$ {valor:.2f}")

    return "\n".join(linhas)


def eh_comando_resumo(texto):
    """Verifica se a mensagem é um pedido de resumo, tipo 'resumo' ou 'resumo 2026-08'."""
    return texto.strip().lower().startswith("resumo") or texto.strip().lower().startswith("/resumo")


def extrair_ano_mes_do_comando(texto):
    """Extrai o mês pedido (ex: '2026-08') do comando, ou usa o mês atual como padrão."""
    match = re.search(r"(\d{4}-\d{2})", texto)
    if match:
        return match.group(1)
    return datetime.now(timezone.utc).strftime("%Y-%m")


def mes_anterior():
    """Calcula o mês anterior ao atual, no formato 'AAAA-MM' (usado no resumo automático)."""
    hoje = datetime.now(timezone.utc)
    primeiro_dia_mes_atual = hoje.replace(day=1)
    ultimo_dia_mes_anterior = primeiro_dia_mes_atual - timedelta(days=1)
    return ultimo_dia_mes_anterior.strftime("%Y-%m")


# ---------------------------------------------------------------------------
# Handler principal
# ---------------------------------------------------------------------------

def processar_mensagem_telegram(mensagem):
    """
    Recebe o objeto 'message' de um update do Telegram, extrai o texto
    (convertendo áudio/foto quando necessário) e devolve (texto, fonte, chat_id).
    """
    chat_id = mensagem["chat"]["id"]

    if "text" in mensagem:
        return mensagem["text"], "texto", chat_id

    if "voice" in mensagem or "audio" in mensagem:
        campo = "voice" if "voice" in mensagem else "audio"
        file_id = mensagem[campo]["file_id"]
        key = f"audios/{uuid.uuid4().hex}.ogg"
        telegram_baixar_arquivo(file_id, key)
        return extrair_texto_audio(key), "audio", chat_id

    if "photo" in mensagem:
        # o Telegram manda várias resoluções; a última é a maior/melhor qualidade
        file_id = mensagem["photo"][-1]["file_id"]
        key = f"imagens/{uuid.uuid4().hex}.jpg"
        telegram_baixar_arquivo(file_id, key)
        return extrair_texto_imagem(key), "imagem", chat_id

    return None, None, chat_id


def lambda_handler(event, context):
    """
    Ponto de entrada. Aceita dois formatos:

    1) Update real do Telegram (webhook), no formato:
       { "update_id": ..., "message": { "chat": {...}, "text"/"voice"/"photo": ... } }
       Se o texto começar com "resumo" (ex: "resumo" ou "resumo 2026-08"),
       responde com o relatório do mês em vez de registrar um gasto novo.

    2) Formato de teste manual (mantido para depuração sem depender do Telegram):
       { "tipo": "texto", "mensagem": "..." }
       { "tipo": "imagem", "key": "imagens/arquivo.jpg" }
       { "tipo": "audio", "key": "audios/arquivo.ogg" }
       { "tipo": "resumo", "ano_mes": "2026-08" }  (ano_mes é opcional; padrão é o mês atual)

    3) Disparo automático do EventBridge Scheduler (resumo mensal sem interação do usuário):
       { "tipo": "resumo_automatico" }
       Calcula o mês anterior sozinho e manda o resumo para TELEGRAM_CHAT_ID.
    """
    body = json.loads(event["body"]) if isinstance(event.get("body"), str) else event

    chat_id = None
    try:
        if "message" in body:
            # --- fluxo real: update do Telegram ---
            mensagem = body["message"]
            chat_id = mensagem["chat"]["id"]

            if "text" in mensagem and eh_comando_resumo(mensagem["text"]):
                ano_mes = extrair_ano_mes_do_comando(mensagem["text"])
                resumo = gerar_resumo(ano_mes)
                telegram_enviar_mensagem(chat_id, formatar_resumo(resumo))
                log_evento("resumo_solicitado", chat_id=chat_id, ano_mes=ano_mes, quantidade=resumo["quantidade"])
                return {"statusCode": 200, "body": json.dumps({"status": "ok", "resumo": ano_mes})}

            texto, fonte, chat_id = processar_mensagem_telegram(mensagem)

            if texto is None:
                telegram_enviar_mensagem(
                    chat_id,
                    "Não entendi esse tipo de mensagem. Manda texto, áudio ou foto do comprovante.",
                )
                log_evento("mensagem_nao_reconhecida", chat_id=chat_id)
                return {"statusCode": 200, "body": json.dumps({"status": "ignorado"})}

            dados = extrair_gasto(texto)

            if dados.get("valor") is None:
                telegram_enviar_mensagem(
                    chat_id,
                    "Não identifiquei um gasto com valor nessa mensagem, então não registrei nada. "
                    "Se foi sem querer, pode ignorar. Se era pra registrar um gasto, tenta mandar de "
                    "novo deixando o valor bem claro.",
                )
                log_evento("gasto_ignorado_sem_valor", chat_id=chat_id, fonte=fonte)
                return {"statusCode": 200, "body": json.dumps({"status": "ignorado_sem_valor"})}

            item = salvar_gasto(dados, texto, fonte=fonte)
            telegram_enviar_mensagem(chat_id, formatar_confirmacao(item))
            log_evento(
                "gasto_registrado",
                chat_id=chat_id,
                fonte=fonte,
                valor=item.get("valor"),
                categoria=item.get("categoria"),
                forma_pagamento=item.get("formaPagamento"),
            )

        else:
            # --- fluxo de teste manual (sem Telegram) / disparo automático do EventBridge ---
            tipo = body.get("tipo", "texto")

            if tipo == "resumo_automatico":
                # Disparado pelo EventBridge Scheduler todo dia 1, sem interação do usuário.
                ano_mes = mes_anterior()
                resumo = gerar_resumo(ano_mes)
                if TELEGRAM_CHAT_ID:
                    telegram_enviar_mensagem(TELEGRAM_CHAT_ID, formatar_resumo(resumo))
                log_evento("resumo_automatico_enviado", ano_mes=ano_mes, quantidade=resumo["quantidade"])
                return {
                    "statusCode": 200,
                    "body": json.dumps({"status": "ok", "resumo_automatico": ano_mes}, default=str),
                }

            if tipo == "resumo":
                ano_mes = body.get("ano_mes") or datetime.now(timezone.utc).strftime("%Y-%m")
                resumo = gerar_resumo(ano_mes)
                return {
                    "statusCode": 200,
                    "body": json.dumps({"status": "ok", "resumo": resumo}, default=str),
                }

            if tipo == "texto":
                texto = body.get("mensagem", "")
                fonte = "texto"
            elif tipo == "imagem":
                texto = extrair_texto_imagem(body["key"])
                fonte = "imagem"
            elif tipo == "audio":
                texto = extrair_texto_audio(body["key"])
                fonte = "audio"
            else:
                return {"statusCode": 400, "body": json.dumps({"erro": f"Tipo desconhecido: {tipo}"})}

            if not texto:
                return {"statusCode": 400, "body": json.dumps({"erro": "Não foi possível extrair texto"})}

            dados = extrair_gasto(texto)

            if dados.get("valor") is None:
                return {
                    "statusCode": 200,
                    "body": json.dumps({"status": "ignorado_sem_valor", "dados_extraidos": dados}, default=str),
                }

            item = salvar_gasto(dados, texto, fonte=fonte)

    except json.JSONDecodeError:
        log_evento("erro_json_invalido", chat_id=chat_id)
        if chat_id:
            telegram_enviar_mensagem(chat_id, "Não consegui entender essa mensagem, tenta de novo com outras palavras.")
        return {
            "statusCode": 500,
            "body": json.dumps({"erro": "O modelo não retornou um JSON válido"}),
        }

    except Exception as e:
        # Qualquer outro erro inesperado (ex: falha de permissão, timeout de outro
        # serviço, etc.) é logado de forma estruturada e depois relançado. Relançar
        # é importante: é isso que faz a invocação contar como "Errors" na métrica
        # do CloudWatch, que é o que aciona o alarme configurado no console.
        log_evento("erro_inesperado", chat_id=chat_id, tipo_erro=type(e).__name__, mensagem=str(e))
        if chat_id:
            telegram_enviar_mensagem(chat_id, "Deu um erro inesperado aqui do meu lado, tenta de novo em instantes.")
        raise

    return {
        "statusCode": 200,
        "body": json.dumps({"status": "ok", "gasto_salvo": item}, default=str),
    }
