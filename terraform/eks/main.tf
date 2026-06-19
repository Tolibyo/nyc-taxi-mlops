


resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
  enable_dns_hostnames = true
  tags = {
    Name = "tripsvc-vpc"
  }
}

resource "aws_subnet" "public_a" {
    vpc_id = aws_vpc.main.id
    cidr_block = "10.0.0.0/24"
    availability_zone = "us-east-1a"
    tags = {
        Name = "tripsvc-public-a"
        "kubernetes.io/role/elb" = "1"
    }
}

resource "aws_subnet" "public_b" {
    vpc_id = aws_vpc.main.id
    cidr_block = "10.0.1.0/24"
    availability_zone = "us-east-1b"
    tags = {
        Name = "tripsvc-public-b"
        "kubernetes.io/role/elb" = "1"
    }
}

resource "aws_subnet" "private_a" {
    vpc_id = aws_vpc.main.id
    cidr_block = "10.0.10.0/24"
    availability_zone = "us-east-1a"
    tags = {
        Name = "tripsvc-private-a"
        "kubernetes.io/role/internal-elb" = "1"
    }
}

resource "aws_subnet" "private_b" {
    vpc_id = aws_vpc.main.id
    cidr_block = "10.0.11.0/24"
    availability_zone = "us-east-1b"
    tags = {
        Name = "tripsvc-private-b"
        "kubernetes.io/role/internal-elb" = "1"
    }
}

resource "aws_internet_gateway" "main" {
    vpc_id = aws_vpc.main.id
    tags = {
        Name = "tripsvc-igw"
    }
}

resource "aws_eip" "nat" {
    domain = "vpc"
    tags =  {
        Name = "tripsvc-nat-eip"
    }
}

resource "aws_nat_gateway" "main" {
    allocation_id = aws_eip.nat.id
    subnet_id = aws_subnet.public_a.id
    depends_on = [ aws_internet_gateway.main ]
    tags = {
        Name = "tripsvc-nat"
    }
}

resource "aws_route_table" "public" {
    vpc_id = aws_vpc.main.id
    route {
        cidr_block = "0.0.0.0/0"
        gateway_id = aws_internet_gateway.main.id
    }
    tags = {
      Name = "tripsvc-public-rt"
    }
}

resource "aws_route_table" "private" {
    vpc_id = aws_vpc.main.id
    route {
        cidr_block = "0.0.0.0/0"
        nat_gateway_id = aws_nat_gateway.main.id
    }
    tags = {
      Name = "tripsvc-private-rt"
    }
}

resource "aws_route_table_association" "public_a" {
    subnet_id = aws_subnet.public_a.id
    route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_b" {
    subnet_id = aws_subnet.public_b.id
    route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private_a" {
    subnet_id = aws_subnet.private_a.id
    route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "private_b" {
    subnet_id = aws_subnet.private_b.id
    route_table_id = aws_route_table.private.id
}

resource "aws_ecr_repository" "tripsvc" {
    name = "tripsvc"
}

output "repository_url" {
    value = aws_ecr_repository.tripsvc.repository_url
}

resource "aws_iam_role" "eks_cluster" {
  name = "tripsvc-eks-cluster-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
        Effect = "Allow"
        Principal = { Service = "eks.amazonaws.com"}
        Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
    role = aws_iam_role.eks_cluster.name
    policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_eks_cluster" "tripsvc" {
    name = "tripsvc"
    role_arn = aws_iam_role.eks_cluster.arn

    vpc_config {
        subnet_ids = [
            aws_subnet.public_a.id,
            aws_subnet.public_b.id,
            aws_subnet.private_a.id,
            aws_subnet.private_b.id,
        ]
    }

    depends_on = [ aws_iam_role_policy_attachment.eks_cluster_policy ]
}

resource "aws_iam_role" "eks_nodes" {
    name = "tripsvc-eks-node-role"
    assume_role_policy = jsonencode({
        Version = "2012-10-17"
        Statement = [{
            Effect = "Allow"
            Principal = { Service = "ec2.amazonaws.com"}
            Action = "sts:AssumeRole"
        }]
    })
}

resource "aws_iam_role_policy_attachment" "node_policies" {
    for_each = toset([
        "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
        "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
        "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
    ])
    role = aws_iam_role.eks_nodes.name
    policy_arn = each.value
}

resource "aws_eks_node_group" "tripsvc" {
    cluster_name = aws_eks_cluster.tripsvc.name
    node_group_name = "tripsvc-nodes"
    node_role_arn = aws_iam_role.eks_nodes.arn

    subnet_ids = [
        aws_subnet.private_a.id,
        aws_subnet.private_b.id,
    ]

    scaling_config {
        desired_size = 2
        min_size = 1
        max_size = 3
    }

    instance_types = [ "t3.medium" ]

    depends_on = [ aws_iam_role_policy_attachment.node_policies ]
}