# DemandHub TEST(H5 Publish) 专用：RocketMQ Broker
# broker.conf 烤进镜像：brokerIP1 注册平台网络别名，namesrv 指向平台 namesrv 别名
# JAVA_OPT=-XX:-UseContainerSupport 经平台 env 注入（cgroup v2 NPE 规避）
FROM apache/rocketmq:5.2.0
COPY broker.conf /home/rocketmq/conf/broker.conf
CMD ["sh", "mqbroker", "-n", "demandhub-rocketmq-namesrv:9876", "-c", "/home/rocketmq/conf/broker.conf"]
