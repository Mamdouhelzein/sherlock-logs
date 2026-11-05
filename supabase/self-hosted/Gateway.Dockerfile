FROM nginx:stable-alpine@sha256:407eb91149b589ca4609f2b61cea90c5b9a0f5578ccf29abad902993700b7255
COPY gateway.conf.template /etc/nginx/templates/default.conf.template
