# Role que a Lambda assume para rodar. A permissão de "quem pode assumir essa
# role" (assume_role_policy) é o serviço Lambda em si.
resource "aws_iam_role" "lambda_ingestao" {
  name = "${var.project_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Projeto = var.project_name
  }
}

# Permissão básica: gravar logs no CloudWatch. Toda Lambda precisa disso.
resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.lambda_ingestao.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# As permissões abaixo usam as policies gerenciadas pela AWS, do jeito que
# foram configuradas manualmente no console durante o desenvolvimento. Numa
# segunda iteração, o ideal seria trocar por policies próprias, restritas só
# às ações e aos recursos (tabela, bucket) que a Lambda realmente usa —
# ficou registrado como próxima melhoria na documentação do projeto.
resource "aws_iam_role_policy_attachment" "bedrock" {
  role       = aws_iam_role.lambda_ingestao.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonBedrockFullAccess"
}

resource "aws_iam_role_policy_attachment" "textract" {
  role       = aws_iam_role.lambda_ingestao.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonTextractFullAccess"
}

resource "aws_iam_role_policy_attachment" "transcribe" {
  role       = aws_iam_role.lambda_ingestao.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonTranscribeFullAccess"
}

resource "aws_iam_role_policy_attachment" "s3" {
  role       = aws_iam_role.lambda_ingestao.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
}

# Permissão de leitura/escrita na tabela DynamoDB, restrita à tabela do projeto.
resource "aws_iam_role_policy" "dynamodb" {
  name = "${var.project_name}-dynamodb-access"
  role = aws_iam_role.lambda_ingestao.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:Query"
        ]
        Resource = aws_dynamodb_table.gastos.arn
      }
    ]
  })
}
