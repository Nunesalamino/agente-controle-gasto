# Tabela de gastos. Chave de partição fixa (uso pessoal, um único usuário) e
# chave de ordenação que embute a data em ISO 8601, o que permite consultar
# um mês inteiro com uma única query eficiente (begins_with no prefixo GASTO#AAAA-MM).
resource "aws_dynamodb_table" "gastos" {
  name         = "Gastos"
  billing_mode = "PAY_PER_REQUEST" # sob demanda: sem custo fixo, ideal para volume baixo e imprevisível

  hash_key  = "PK"
  range_key = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  tags = {
    Projeto = var.project_name
  }
}
