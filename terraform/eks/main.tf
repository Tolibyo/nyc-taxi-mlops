


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
