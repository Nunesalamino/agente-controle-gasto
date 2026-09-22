# Infraestrutura como código (Terraform)

Esta pasta descreve, em Terraform, a mesma infraestrutura que hoje roda em produção configurada manualmente pelo console da AWS: Lambda, API Gateway, DynamoDB, S3, IAM e o EventBridge Scheduler do resumo automático mensal.

**Importante:** este código é uma descrição fiel da infraestrutura para fins de portfólio e aprendizado — **ele não foi aplicado** contra os recursos reais em produção, e não deve ser rodado (`terraform apply`) apontando para a mesma conta/região sem antes ajustar os nomes dos recursos (a tabela `Gastos` e a função `agente-gastos-ingestao-gastos`, por exemplo, colidiriam com os recursos que já existem).

## Estrutura

| Arquivo | O que descreve |
|---|---|
| `providers.tf` | Provider da AWS e versão do Terraform exigida |
| `variables.tf` | Parâmetros de entrada (região, nomes, segredos do Telegram) |
| `dynamodb.tf` | Tabela `Gastos` (PK/SK) |
| `s3.tf` | Bucket de trânsito para áudios/fotos, com expiração automática dos arquivos |
| `iam.tf` | Role e permissões da Lambda |
| `lambda.tf` | Função Lambda, empacotando `lambda_ingestao.py` |
| `api_gateway.tf` | HTTP API que recebe o webhook do Telegram |
| `eventbridge.tf` | Agendamento do resumo mensal automático |
| `outputs.tf` | Valores úteis após o `apply` (ex: URL do webhook) |

## Como usar (se quiser testar num ambiente separado)

1. Instala o [Terraform](https://developer.hashicorp.com/terraform/install).
2. Copia `terraform.tfvars.example` para `terraform.tfvars` e preenche com valores reais — **usando um bot e um bucket diferentes dos de produção**, pra não colidir com o que já existe.
3. Roda:
   ```bash
   terraform init    # baixa os providers necessários
   terraform plan    # mostra o que seria criado, sem criar nada ainda
   terraform apply   # cria de fato os recursos na AWS
   ```
4. Depois do `apply`, pega a `webhook_url` na saída e configura no Telegram com `setWebhook`.
5. Quando terminar de testar, `terraform destroy` remove tudo que foi criado.
