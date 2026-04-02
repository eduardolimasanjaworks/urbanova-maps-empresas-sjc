# Urbanova Terminal Web (xterm.js)

Terminal web restrito para operar somente a ferramenta Urbanova.

## O que este projeto faz

- Login com usuario/senha.
- Exibe um terminal no navegador via `xterm.js`.
- Bloqueia shell livre: aceita apenas comandos allowlist:
  - `urbanova help`
  - `urbanova status`
  - `urbanova cost --nearby N --text N --details N`
  - `urbanova run [parametros permitidos]`
  - `urbanova export`
- Permite baixar o CSV gerado em `/download/csv`.

## 1) Instalar

```bash
cd terminal-web
npm install
```

## 2) Configurar

```bash
copy .env.example .env
```

Gere hash da senha:

```bash
node hash-password.js SuaSenhaForte
```

Cole o hash em `TERMINAL_PASSWORD_HASH` no `.env`.

Se a pasta da ferramenta estiver no diretório pai (padrão), mantenha:

```env
TOOL_DIR=..
```

## 3) Rodar

```bash
npm start
```

Abra:

- `http://localhost:8787`

## 4) Publicar em domínio (produção)

- Coloque um reverse proxy com HTTPS (Nginx/Caddy/Traefik).
- Habilite firewall.
- Troque `SESSION_SECRET`.
- Use senha forte.
- Recomenda-se rodar em VM/container isolado.

## 5) Segurança

- Este terminal já é restrito por allowlist.
- Mesmo assim, mantenha o servidor em ambiente controlado.
- Nunca exponha chaves da Google API no frontend.
