# Bucket usado só como área de trânsito: os áudios e fotos recebidos do
# Telegram passam por aqui para o Textract/Transcribe conseguirem lê-los
# (ambos exigem que o arquivo esteja no S3, não aceitam o binário direto).
resource "aws_s3_bucket" "midia" {
  bucket = var.s3_bucket_name

  tags = {
    Projeto = var.project_name
  }
}

# Como os arquivos são só um passo intermediário do processamento (o dado
# que importa já foi extraído e salvo no DynamoDB), não há motivo para
# guardá-los indefinidamente — isso é uma melhoria em relação ao bucket
# criado manualmente, que não tinha essa expiração configurada.
resource "aws_s3_bucket_lifecycle_configuration" "midia_expiracao" {
  bucket = aws_s3_bucket.midia.id

  rule {
    id     = "expirar-midia-processada"
    status = "Enabled"

    filter {
      prefix = "" # aplica a tudo no bucket (pastas audios/ e imagens/)
    }

    expiration {
      days = 7
    }
  }
}
