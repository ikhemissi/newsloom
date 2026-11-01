FROM docker.io/library/node@sha256:a43f7fc3e52e87d12a905f46eea0275def84ca8f2981a5b53fed44d7fb398ee0 AS build
WORKDIR /workspace
COPY package.json package-lock.json ./
COPY services/web/package.json services/web/package.json
RUN npm ci --no-audit --no-fund
COPY services/web services/web
RUN npm run -w services/web build

FROM mcr.microsoft.com/playwright@sha256:d65108d1a8095d8b0c4a5e32bf1807a40a5ce90ff0c78473e1116b1c243235e8 AS browser-check
COPY --from=build /usr/local/bin/node /usr/local/bin/node
COPY --from=build /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
COPY --from=build /workspace /workspace
WORKDIR /workspace
CMD ["node", "/usr/local/lib/node_modules/npm/bin/npm-cli.js", "run", "-w", "services/web", "e2e:local"]

FROM docker.io/nginxinc/nginx-unprivileged@sha256:e2a8fca8aa356d66159aaf8a877a9c126773635adf210503eefaaeaffeed6ad7 AS production
COPY --from=build /workspace/services/web/dist /usr/share/nginx/html
COPY services/web/nginx.conf /opt/newsloom/nginx.conf
COPY services/web/headers.conf.template /opt/newsloom/headers.conf.template
COPY services/web/entrypoint.sh /opt/newsloom/entrypoint.sh
USER 0:0
RUN chmod 0555 /opt/newsloom/entrypoint.sh
USER 101:101
EXPOSE 8080
ENTRYPOINT ["/opt/newsloom/entrypoint.sh"]
