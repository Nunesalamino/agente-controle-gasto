variable "aws_region" {
  description = "Região da AWS onde os recursos serão criados."
  type        = string
  default     = "us-east-2"
}

variable "project_name" {
  description = "Prefixo usado no nome dos recursos, para diferenciar deploys (ex: prod, dev, teste-terraform)."
  type        = string
  default     = "agente-gastos"
}

variable "telegram_bot_token" {
  description = "Token do bot do Telegram (obtido via BotFather). Sensível: não deve ir para o controle de versão em texto puro."
  type        = string
  sensitive   = true
}

variable "telegram_chat_id" {
  description = "ID do chat do Telegram para onde o resumo automático mensal é enviado."
  type        = string
}

variable "s3_bucket_name" {
  description = "Nome do bucket S3 usado para armazenar áudios e imagens recebidos (precisa ser globalmente único)."
  type        = string
}

variable "alert_email" {
  description = "E-mail que recebe os alarmes do CloudWatch (erros da Lambda e gastos estimados da conta)."
  type        = string
}

variable "billing_alarm_threshold" {
  description = "Valor limite (em USD) de encargos estimados no mês a partir do qual o alarme de billing dispara."
  type        = number
  default     = 5
}
