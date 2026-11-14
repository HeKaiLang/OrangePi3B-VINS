# 1. 移除失效的 USTC mirror（先备份）
sudo cp /etc/docker/daemon.json /etc/docker/daemon.json.bak
sudo cp /tmp/daemon.json /etc/docker/daemon.json

# 2. 给 docker daemon 配代理（拉镜像走 192.168.137.1:7897）
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo cp /tmp/docker-http-proxy.conf /etc/systemd/system/docker.d/http-proxy.conf
sudo systemctl daemon-reload
sudo systemctl restart docker
