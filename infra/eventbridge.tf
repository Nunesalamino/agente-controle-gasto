# Role que o EventBridge Scheduler assume para poder invocar a Lambda.
# Equivalente ao perfil que o console criou automaticamente ao configurar
# o cronograma pela interface gráfica.
resource "aws_iam_role" "scheduler" {
  name = "${var.project_name}-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "scheduler.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "scheduler_invoke_lambda" {
  name = "${var.project_name}-scheduler-invoke-lambda"
  role = aws_iam_role.scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "lambda:InvokeFunction"
        Resource = aws_lambda_function.ingestao_gastos.arn
      }
    ]
  })
}

# Todo dia 1 de cada mês, às 9h no horário de Brasília, invoca a Lambda
# pedindo o resumo automático do mês anterior.
resource "aws_scheduler_schedule" "resumo_mensal" {
  name       = "${var.project_name}-resumo-mensal"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "cron(0 9 1 * ? *)"
  schedule_expression_timezone = "America/Sao_Paulo"

  target {
    arn      = aws_lambda_function.ingestao_gastos.arn
    role_arn = aws_iam_role.scheduler.arn

    input = jsonencode({
      tipo = "resumo_automatico"
    })
  }
}
