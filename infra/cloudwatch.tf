# Monitoramento: dois alarmes configurados manualmente no console durante o
# desenvolvimento, descritos aqui em código para manter a infraestrutura
# fiel ao que roda em produção.
#
# 1. Erros da Lambda de ingestão (namespace AWS/Lambda), que dispara se a
#    função lançar 1 ou mais erros em uma janela de 5 minutos.
# 2. Gastos estimados da conta AWS (namespace AWS/Billing), que dispara se
#    o total de encargos estimados no mês ultrapassar um valor limite.
#
# A métrica de billing só existe na região us-east-1, independentemente da
# região onde os outros recursos rodam (aqui, us-east-2) — por isso o
# alarme de billing usa um provider separado, com alias "billing".

provider "aws" {
  alias  = "billing"
  region = "us-east-1"
}

# Tópico SNS único para os dois alarmes, com notificação por e-mail.
resource "aws_sns_topic" "alertas" {
  name = "${var.project_name}-alertas"

  tags = {
    Projeto = var.project_name
  }
}

resource "aws_sns_topic_subscription" "alertas_email" {
  topic_arn = aws_sns_topic.alertas.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# Alarme 1: erros da Lambda de ingestão.
resource "aws_cloudwatch_metric_alarm" "erros_lambda" {
  alarm_name          = "${var.project_name}-erros-lambda"
  alarm_description   = "Dispara quando a Lambda de ingestão lança 1 ou mais erros em 5 minutos."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions = {
    FunctionName = aws_lambda_function.ingestao_gastos.function_name
  }
  statistic           = "Sum"
  period              = 300 # 5 minutos
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alertas.arn]
  ok_actions    = [aws_sns_topic.alertas.arn]

  tags = {
    Projeto = var.project_name
  }
}

# Alarme 2: gastos estimados da conta (billing). Precisa do provider em
# us-east-1 e de "Receber alertas de faturamento do CloudWatch" habilitado
# em Faturamento e Gerenciamento de Custos -> Preferências de faturamento.
resource "aws_cloudwatch_metric_alarm" "gastos_billing" {
  provider = aws.billing

  alarm_name          = "alerta-gastos-billing"
  alarm_description   = "Dispara quando os encargos estimados da conta AWS no mês ultrapassam o valor limite."
  namespace           = "AWS/Billing"
  metric_name         = "EstimatedCharges"
  dimensions = {
    Currency = "USD"
  }
  statistic           = "Maximum"
  period              = 21600 # 6 horas
  evaluation_periods  = 1
  threshold           = var.billing_alarm_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "missing"

  alarm_actions = [aws_sns_topic.alertas.arn]

  tags = {
    Projeto = var.project_name
  }
}
