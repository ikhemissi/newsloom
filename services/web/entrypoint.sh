#!/bin/sh
set -eu
if ! printf '%s' "${AGENT_ORIGIN:-}" | grep -Eq '^https://[a-z0-9]+([.-][a-z0-9]+)*$'; then
  printf '%s\n' 'ui_origin_configuration_invalid' >&2
  exit 1
fi
if [ -z "${UI_CONFIG_BASE64:-}" ] || ! printf '%s' "$UI_CONFIG_BASE64" | base64 -d > /tmp/newsloom-config.json 2>/dev/null; then
  printf '%s\n' 'ui_configuration_invalid' >&2
  exit 1
fi
if [ -n "${MCP_ORIGIN:-}" ] && ! printf '%s' "$MCP_ORIGIN" | grep -Eq '^https://[a-z0-9]+([.-][a-z0-9]+)*$'; then
  printf '%s\n' 'ui_mcp_origin_configuration_invalid' >&2
  exit 1
fi
envsubst '${AGENT_ORIGIN} ${MCP_ORIGIN}' < /opt/newsloom/headers.conf.template > /tmp/newsloom-headers.conf
exec nginx -c /opt/newsloom/nginx.conf -g 'daemon off;'
