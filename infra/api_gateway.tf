# HTTP API que recebe o webhook do Telegram e repassa para a Lambda.
resource "aws_apigatewayv2_api" "webhook" {
  name          = "${var.project_name}-webhook"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.webhook.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.ingestao_gastos.invoke_arn
  payload_format_version = "2.0"
}

# Rota "pega tudo": qualquer método HTTP na raiz vai para a Lambda. O Telegram
# sempre manda o update via POST, mas ANY evita ter que declarar cada verbo.
resource "aws_apigatewayv2_route" "root" {
  api_id    = aws_apigatewayv2_api.webhook.id
  route_key = "ANY /"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.webhook.id
  name        = "$default"
  auto_deploy = true
}

# Autoriza o API Gateway a invocar a Lambda. Sem isso, a integração existe
# mas toda chamada do Telegram falha com "acesso negado" internamente.
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingestao_gastos.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.webhook.execution_arn}/*/*"
}
