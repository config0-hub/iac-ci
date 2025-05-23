#!/bin/bash -x

export INSTANCE_ID="$(/opt/aws/bin/ec2-metadata -i | cut -d' ' -f2)"
export AVAIL_ZONE="$(/opt/aws/bin/ec2-metadata -z | cut -d' ' -f2)"
export AWS_DEFAULT_REGION="$(/opt/aws/bin/ec2-metadata -z  | sed 's/placement: \(.*\).$/\1/')"
aws ec2 modify-instance-attribute --no-source-dest-check --instance-id $INSTANCE_ID --region $AWS_DEFAULT_REGION

sysctl -q -w net.ipv4.ip_forward=1
yum install iptables-services -y
systemctl enable iptables
systemctl start iptables
/sbin/iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
/sbin/iptables -F FORWARD
service iptables save

aws ec2 create-route --route-table-id "${route_table_id}" --destination-cidr-block 0.0.0.0/0 --instance-id $INSTANCE_ID --region $AWS_DEFAULT_REGION > /dev/null 2>&1 || aws ec2 replace-route --route-table-id "${route_table_id}" --destination-cidr-block 0.0.0.0/0 --instance-id $INSTANCE_ID --region $AWS_DEFAULT_REGION
