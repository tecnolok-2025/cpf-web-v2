# Configuración de envío de emails (CPF) en Render

## Importante
Render **no provee** una casilla de correo tipo `cpf-requerimiento@render.com` para enviar/recibir emails.
Para que CPF pueda enviar notificaciones, necesitás usar un **proveedor externo** (SMTP o API de emails), por ejemplo:
- Gmail (con *App Password*)
- Outlook/Microsoft 365
- Un dominio propio (Google Workspace / Microsoft 365 / Zoho)
- Proveedores de envío: SendGrid, Mailgun, Amazon SES, Resend, etc.

CPF envía emails **solo** si se configuran variables de entorno en Render.

---

## Opción recomendada (rápida): Gmail con App Password

### Requisitos
- Tener verificación en 2 pasos activada en la cuenta Google.
- Crear una *Contraseña de aplicación* (App Password).

### Variables a cargar en Render
En Render → Service → **Environment** → Add Environment Variable:

- `CPF_SMTP_HOST` = `smtp.gmail.com`
- `CPF_SMTP_PORT` = `587`
- `CPF_SMTP_USER` = tu Gmail (ej: `tuusuario@gmail.com`)
- `CPF_SMTP_PASS` = App Password (16 caracteres, sin espacios)
- `CPF_SMTP_FROM` = `CPF <tuusuario@gmail.com>`  (o el remitente que quieras)
- `CPF_APP_URL` = `https://cpf-web.onrender.com`

Luego: **Manual Deploy → Clear build cache & deploy** (o redeploy normal).

---

## Opción con dominio propio (SMTP)
Pedile a tu proveedor los datos SMTP y cargalos igual:

- `CPF_SMTP_HOST` = (host smtp)
- `CPF_SMTP_PORT` = `587` (o `465` si SSL)
- `CPF_SMTP_USER` = (usuario)
- `CPF_SMTP_PASS` = (clave)
- `CPF_SMTP_FROM` = `CPF <notificaciones@tudominio.com>`
- `CPF_APP_URL` = `https://cpf-web.onrender.com`

---

## Cómo verificar que está funcionando
1) Entrá a Render → Service → **Logs**
2) En CPF:
   - Creá un “Interés” en una publicación
   - Aceptalo
3) Si SMTP está mal, verás errores (auth/timeout).
   Si está bien, llegará el email y en logs verás “Email enviado” (según configuración).

---

## Nota sobre “correo @render.com”
Render hospeda aplicaciones, pero **no** es un proveedor de email.
Si querés un email “institucional” (ej: `notificaciones@corredorproductivofederal.org`),
la mejor práctica es crear un dominio y usar un proveedor (Workspace/M365/Zoho o SendGrid/Mailgun/SES).
