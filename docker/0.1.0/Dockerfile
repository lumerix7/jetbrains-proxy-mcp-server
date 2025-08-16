FROM python:3.13.7-slim

ENV LANG=en_US.utf8
ENV TZ=Asia/Shanghai

ARG EXTRA_INDEX_URL
ARG EXTRA_INDEX_HOST

RUN pip install jetbrains-proxy-mcp-server --no-cache-dir --extra-index-url $EXTRA_INDEX_URL --trusted-host=$EXTRA_INDEX_HOST

EXPOSE 41110
WORKDIR /root

CMD ["jetbrains-proxy-mcp-server"]
