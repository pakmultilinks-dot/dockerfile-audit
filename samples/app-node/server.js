const express = require("express");

const app = express();
const port = 3000;

app.get("/", (req, res) => res.json({ status: "ok", service: "app-node" }));
app.get("/health", (req, res) => res.json({ status: "healthy" }));

app.listen(port, "0.0.0.0", () => console.log(`listening on ${port}`));
