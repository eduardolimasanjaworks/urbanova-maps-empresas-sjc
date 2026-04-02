const bcrypt = require("bcryptjs");

const password = process.argv[2];
if (!password) {
  console.error("Uso: node hash-password.js SUA_SENHA");
  process.exit(1);
}

const hash = bcrypt.hashSync(password, 10);
console.log(hash);
