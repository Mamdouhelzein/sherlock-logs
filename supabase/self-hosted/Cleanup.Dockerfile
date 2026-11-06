FROM postgres:17-alpine@sha256:562a6e0a66b5136bc28bef5944bbc2ddddf8ea0058d4016b96cee63f2edaf143
COPY --chmod=0444 cleanup.sh /usr/local/bin/sherlock-cleanup
USER postgres
ENTRYPOINT ["/bin/sh", "/usr/local/bin/sherlock-cleanup"]
