#!/usr/bin/env python3
"""
Improved Windows-compatible approach for Nautilus deployment
This handles all the functionality of configure_enclave.sh but works on Windows
"""

import boto3
import json
import time
import os
import yaml
import subprocess
import sys
from pathlib import Path

class ImprovedNautilusDeployer:
    def __init__(self, config):
        self.config = config
        self.region = config.get('region', 'us-east-1')
        self.ec2_client = boto3.client('ec2', region_name=self.region)
        self.secrets_client = boto3.client('secretsmanager', region_name=self.region)
        self.iam_client = boto3.client('iam', region_name=self.region)
        
    def load_endpoints(self):
        """Load endpoints from allowed_endpoints.yaml"""
        endpoints_file = Path("src/nautilus-server/allowed_endpoints.yaml")
        if endpoints_file.exists():
            with open(endpoints_file, 'r') as f:
                data = yaml.safe_load(f)
                endpoints = data.get('endpoints', [])
                
                # Replace region-specific AWS endpoints
                updated_endpoints = []
                for endpoint in endpoints:
                    if 'kms.' in endpoint and '.amazonaws.com' in endpoint:
                        endpoint = f"kms.{self.region}.amazonaws.com"
                    elif 'secretsmanager.' in endpoint and '.amazonaws.com' in endpoint:
                        endpoint = f"secretsmanager.{self.region}.amazonaws.com"
                    updated_endpoints.append(endpoint)
                
                return updated_endpoints
        return []
    
    def create_iam_role(self, role_name, secret_arn=None):
        """Create IAM role for EC2 instance"""
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        
        try:
            # Create role
            self.iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy)
            )
            print(f"✓ Created IAM role: {role_name}")
            
            # Add secrets policy if secret is used
            if secret_arn:
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "secretsmanager:GetSecretValue",
                                "secretsmanager:DescribeSecret"
                            ],
                            "Resource": secret_arn
                        }
                    ]
                }
                
                self.iam_client.put_role_policy(
                    RoleName=role_name,
                    PolicyName=f"{role_name}-secrets-policy",
                    PolicyDocument=json.dumps(policy)
                )
                print(f"✓ Added secrets policy to role")
            
            # Create instance profile
            self.iam_client.create_instance_profile(InstanceProfileName=role_name)
            self.iam_client.add_role_to_instance_profile(
                InstanceProfileName=role_name,
                RoleName=role_name
            )
            print(f"✓ Created instance profile: {role_name}")
            
            # Wait for instance profile to be ready
            print("⏳ Waiting for IAM role to propagate...")
            time.sleep(15)
            
            return role_name
            
        except Exception as e:
            if 'already exists' in str(e).lower():
                print(f"✓ Using existing IAM role: {role_name}")
                return role_name
            else:
                print(f"❌ Error creating IAM role: {e}")
                raise
    
    def create_security_group(self):
        """Create security group for Nautilus"""
        sg_name = "instance-script-sg"
        
        try:
            # Check if security group already exists
            try:
                response = self.ec2_client.describe_security_groups(GroupNames=[sg_name])
                security_group_id = response['SecurityGroups'][0]['GroupId']
                print(f"✓ Using existing security group: {security_group_id}")
                return security_group_id
            except:
                pass
            
            # Create new security group
            response = self.ec2_client.create_security_group(
                GroupName=sg_name,
                Description='Security group allowing SSH (22), HTTPS (443), and port 3000'
            )
            
            security_group_id = response['GroupId']
            
            # Add rules
            self.ec2_client.authorize_security_group_ingress(
                GroupId=security_group_id,
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 22,
                        'ToPort': 22,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 3000,
                        'ToPort': 3000,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 443,
                        'ToPort': 443,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    }
                ]
            )
            
            print(f"✓ Created security group: {security_group_id}")
            return security_group_id
            
        except Exception as e:
            print(f"❌ Error creating security group: {e}")
            raise
    
    def create_secret(self):
        """Create secret in AWS Secrets Manager"""
        if not self.config.get('use_secret', False):
            return None
            
        secret_name = self.config['secret_name']
        secret_value = self.config['secret_value']
        
        try:
            response = self.secrets_client.create_secret(
                Name=secret_name,
                SecretString=secret_value
            )
            print(f"✓ Created secret: {response['ARN']}")
            return response['ARN']
        except Exception as e:
            if 'already exists' in str(e).lower():
                response = self.secrets_client.describe_secret(SecretId=secret_name)
                print(f"✓ Using existing secret: {response['ARN']}")
                return response['ARN']
            else:
                print(f"❌ Error creating secret: {e}")
                raise
    
    def update_expose_enclave_script(self, secret_arn, role_name):
        """Update expose_enclave.sh with secret fetching logic"""
        if not secret_arn:
            return
            
        script_path = Path("expose_enclave.sh")
        if not script_path.exists():
            print("❌ expose_enclave.sh not found")
            return
            
        with open(script_path, 'r') as f:
            content = f.read()
        
        # Remove existing secret lines
        lines = content.split('\n')
        filtered_lines = []
        for line in lines:
            if 'SECRET_VALUE=' not in line and 'secrets.json' not in line:
                filtered_lines.append(line)
        
        # Find the secrets block and add new lines
        new_lines = []
        for line in filtered_lines:
            new_lines.append(line)
            if '# Secrets-block' in line:
                new_lines.append(f'SECRET_VALUE=$(aws secretsmanager get-secret-value --secret-id {secret_arn} --region {self.region} | jq -r .SecretString)')
                new_lines.append('echo "$SECRET_VALUE" | jq -R \'{"API_KEY": .}\' > secrets.json')
        
        with open(script_path, 'w') as f:
            f.write('\n'.join(new_lines))
        
        print("✓ Updated expose_enclave.sh with secret fetching logic")
    
    def generate_user_data(self, endpoints):
        """Generate comprehensive user data script"""
        
        user_data_lines = [
            "#!/bin/bash",
            "# Update system",
            "sudo yum update -y",
            "",
            "# Install dependencies", 
            "sudo yum install -y aws-nitro-enclaves-cli-devel aws-nitro-enclaves-cli docker nano socat git make jq",
            "",
            "# Add user to groups",
            "sudo usermod -aG docker ec2-user",
            "sudo usermod -aG ne ec2-user",
            "",
            "# Start and enable services",
            "sudo systemctl start docker",
            "sudo systemctl enable docker",
            "sudo systemctl start nitro-enclaves-allocator.service",
            "sudo systemctl enable nitro-enclaves-allocator.service",
            "sudo systemctl enable nitro-enclaves-vsock-proxy.service",
            ""
        ]
        
        # Add endpoint configuration
        if endpoints:
            for endpoint in endpoints:
                user_data_lines.append(f'echo "- {{address: {endpoint}, port: 443}}" | sudo tee -a /etc/nitro_enclaves/vsock-proxy.yaml')
        
        user_data_lines.extend([
            "",
            "# Stop the allocator so we can modify its configuration",
            "sudo systemctl stop nitro-enclaves-allocator.service",
            "",
            "# Adjust the enclave allocator memory (default set to 3072 MiB)",
            "ALLOCATOR_YAML=/etc/nitro_enclaves/allocator.yaml",
            "MEM_KEY=memory_mib",
            "DEFAULT_MEM=3072",
            'sudo sed -r "s/^(\\s*${MEM_KEY}\\s*:\\s*).*/\\1${DEFAULT_MEM}/" -i "${ALLOCATOR_YAML}"',
            "",
            "# Restart the allocator with the updated memory configuration",
            "sudo systemctl start nitro-enclaves-allocator.service",
            "sudo systemctl enable nitro-enclaves-allocator.service",
            ""
        ])
        
        # Add vsock-proxy processes for endpoints
        if endpoints:
            port = 8101
            for endpoint in endpoints:
                user_data_lines.append(f"vsock-proxy {port} {endpoint} 443 --config /etc/nitro_enclaves/vsock-proxy.yaml &")
                port += 1
        
        return '\n'.join(user_data_lines)
    
    def launch_instance(self, security_group_id, endpoints, secret_arn=None, iam_role=None):
        """Launch EC2 instance with Nitro Enclave support"""
        
        user_data = self.generate_user_data(endpoints)
        
        # Generate instance name with random suffix
        import random
        random_suffix = random.randint(100000, 999999)
        instance_name = f"{self.config['instance_name']}-{random_suffix}"
        
        launch_params = {
            'ImageId': self.config.get('ami_id', 'ami-085ad6ae776d8f09c'),
            'InstanceType': 'm5.xlarge',
            'KeyName': self.config['key_pair'],
            'SecurityGroupIds': [security_group_id],
            'MinCount': 1,
            'MaxCount': 1,
            'UserData': user_data,
            'EnclaveOptions': {'Enabled': True},
            'BlockDeviceMappings': [
                {
                    'DeviceName': '/dev/xvda',
                    'Ebs': {
                        'VolumeSize': 200,
                        'VolumeType': 'gp3'
                    }
                }
            ],
            'TagSpecifications': [
                {
                    'ResourceType': 'instance',
                    'Tags': [
                        {'Key': 'Name', 'Value': instance_name},
                        {'Key': 'instance-script', 'Value': 'true'}
                    ]
                }
            ]
        }
        
        # Add IAM instance profile if available
        if iam_role:
            launch_params['IamInstanceProfile'] = {'Name': iam_role}
        
        print(f"🚀 Launching EC2 instance: {instance_name}")
        response = self.ec2_client.run_instances(**launch_params)
        
        instance_id = response['Instances'][0]['InstanceId']
        print(f"✓ Launched instance: {instance_id}")
        
        # Wait for instance to be running
        print("⏳ Waiting for instance to be running...")
        waiter = self.ec2_client.get_waiter('instance_running')
        waiter.wait(InstanceIds=[instance_id])
        
        # Associate IAM instance profile if needed
        if iam_role:
            try:
                self.ec2_client.associate_iam_instance_profile(
                    InstanceId=instance_id,
                    IamInstanceProfile={'Name': iam_role}
                )
                print(f"✓ Associated IAM instance profile")
            except Exception as e:
                print(f"⚠️  Warning: Could not associate IAM profile: {e}")
        
        time.sleep(10)
        
        # Get public IP
        response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
        public_ip = response['Reservations'][0]['Instances'][0]['PublicIpAddress']
        
        print(f"✓ Instance ready: {public_ip}")
        return instance_id, public_ip, instance_name
    
    def deploy(self):
        """Main deployment flow"""
        print("🌊 === Starting Nautilus Deployment on AWS Nitro Enclave ===")
        print(f"📍 Region: {self.region}")
        print(f"🔑 Key Pair: {self.config['key_pair']}")
        
        try:
            # Load endpoints
            endpoints = self.load_endpoints()
            print(f"🌐 Loaded {len(endpoints)} endpoints: {endpoints}")
            
            # Create secret if needed
            secret_arn = None
            iam_role = None
            
            if self.config.get('use_secret', False):
                secret_arn = self.create_secret()
                
                # Create IAM role for secret access
                role_name = f"role-{self.config['instance_name']}-{int(time.time())}"
                iam_role = self.create_iam_role(role_name, secret_arn)
                
                # Update expose_enclave.sh
                self.update_expose_enclave_script(secret_arn, iam_role)
            
            # Create security group
            security_group_id = self.create_security_group()
            
            # Launch instance
            instance_id, public_ip, instance_name = self.launch_instance(
                security_group_id, endpoints, secret_arn, iam_role
            )
            
            # Save deployment info
            deployment_info = {
                'instance_id': instance_id,
                'instance_name': instance_name,
                'public_ip': public_ip,
                'security_group_id': security_group_id,
                'secret_arn': secret_arn,
                'iam_role': iam_role,
                'region': self.region,
                'endpoints': endpoints,
                'timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            with open('nautilus_deployment_info.json', 'w') as f:
                json.dump(deployment_info, f, indent=2)
            
            print("\n🎉 === Deployment Complete ===")
            print(f"🖥️  Instance ID: {instance_id}")
            print(f"🌐 Public IP: {public_ip}")
            print(f"🔒 Security Group: {security_group_id}")
            if secret_arn:
                print(f"🔐 Secret ARN: {secret_arn}")
                print(f"👤 IAM Role: {iam_role}")
            
            print("\n📋 Next Steps:")
            print("1. ⏰ Wait 10-15 minutes for instance setup to complete")
            print(f"2. 🔌 SSH into instance:")
            print(f"   ssh -i ~/.ssh/{self.config['key_pair']}.pem ec2-user@{public_ip}")
            print("3. 📁 Clone this repository to the instance:")
            print("   git clone <your-repo-url>")
            print("   cd nautilus-deployment")
            print("4. 🔨 Build and run the enclave:")
            print("   make")
            print("   make run")
            print("5. 🌐 In another terminal, expose the enclave:")
            print("   ./expose_enclave.sh")
            print(f"6. 🧪 Test the service:")
            print(f"   curl http://{public_ip}:3000/health_check")
            
            return True
            
        except Exception as e:
            print(f"❌ Deployment failed: {e}")
            return False

def main():
    if len(sys.argv) != 2:
        print("Usage: python nautilus_deploy_improved.py <config_file>")
        print("Example: python nautilus_deploy_improved.py nautilus_config_template.json")
        sys.exit(1)
    
    config_file = sys.argv[1]
    
    if not os.path.exists(config_file):
        print(f"❌ Config file not found: {config_file}")
        sys.exit(1)
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        # Validate required fields
        required_fields = ['key_pair', 'region', 'instance_name']
        for field in required_fields:
            if field not in config:
                print(f"❌ Missing required field in config: {field}")
                sys.exit(1)
        
        deployer = ImprovedNautilusDeployer(config)
        success = deployer.deploy()
        
        if success:
            print("\n✅ Deployment completed successfully!")
        else:
            print("\n❌ Deployment failed!")
            sys.exit(1)
            
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in config file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 