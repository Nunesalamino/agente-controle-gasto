# Empacota o arquivo lambda_ingestao.py (na raiz do repositório) num .zip,
# que é o formato que a Lambda espera para o deploy.
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../lambda_ingestao.py"
  output_path = "${path.module}/lambda_ingestao.zip"
}

resource "aws_lambda_function" "ingestao_gastos" {
  function_name = "${var.project_name}-ingestao-gastos"
  role          = aws_iam_role.lambda_ingestao.arn
  handler       = "lambda_ingestao.lambda_handler"
  runtime       = "python3.13"
  timeout       = 60 # a transcrição de áudio faz polling e pode levar um tempo

  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      TABLE_NAME         = aws_dynamodb_table.gastos.name
      BUCKET_NAME         = aws_s3_bucket.midia.bucket
      TELEGRAM_BOT_TOKEN  = var.telegram_bot_token
      TELEGRAM_CHAT_ID    = var.telegram_chat_id
    }
  }

  tags = {
    Projeto = var.project_name
  }
}
