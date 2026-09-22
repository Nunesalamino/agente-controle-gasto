output "webhook_url" {
  description = "URL a ser configurada no setWebhook do Telegram."
  value       = aws_apigatewayv2_api.webhook.api_endpoint
}

output "lambda_function_name" {
  value = aws_lambda_function.ingestao_gastos.function_name
}

output "dynamodb_table_name" {
  value = aws_dynamodb_table.gastos.name
}

output "s3_bucket_name" {
  value = aws_s3_bucket.midia.bucket
}
