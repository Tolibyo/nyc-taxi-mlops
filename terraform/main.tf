



terraform {
    required_providers {
        aws = {
            source = "hashicorp/aws"
            version = "~> 5.0"
        }
    }

    backend "s3" {
        bucket = "nyc-taxi-tfstate"
        key = "terraform.tfstate"
        region = "us-east-1"
        skip_credentials_validation = true
        skip_metadata_api_check = true
        skip_region_validation = true
        use_path_style = true
        skip_requesting_account_id = true
        endpoints = {
            s3 = "http://localhost:4566"
            iam = "http://localhost:4566"
            sts = "http://localhost:4566"
        }

        use_lockfile = true
    }
}

provider "aws" {
    region = "us-east-1"
    access_key = "test"
    secret_key = "test"
    skip_credentials_validation = true
    skip_requesting_account_id = true
    s3_use_path_style = true

endpoints {
    s3 = "http://localhost:4566"
    iam = "http://localhost:4566"
    sts = "http://localhost:4566"
  }
}

resource "aws_s3_bucket" "model_store" {
  bucket = var.bucket_name
}



resource "aws_iam_policy" "model_read" {
    name = "taxi-model-read"
    policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
            {
                Effect = "Allow"
                Action = ["s3:GetObject"]
                Resource = "${aws_s3_bucket.model_store.arn}/*"
            }
        ]
    })
}


resource "aws_iam_role" "serving_role" {
    name = "taxi-serving-role"
    assume_role_policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
            {
                Effect = "Allow"
                Principal = { Service = "ec2.amazonaws.com" }
                Action = "sts:AssumeRole"
            }
        ]
    })
}

resource "aws_iam_role_policy_attachment" "attach" {
    role = aws_iam_role.serving_role.name
    policy_arn = aws_iam_policy.model_read.arn
}