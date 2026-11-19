import { test } from "node:test";
import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";
import { createApp } from "../src/app.ts";

test("API responde e cria itens", async () => {
  const server = createApp().listen(0);
  try {
    const { port } = server.address() as AddressInfo;
    const base = `http://127.0.0.1:${port}`;

    const health = await fetch(`${base}/health`);
    assert.equal(health.status, 200);
    assert.deepEqual(await health.json(), { status: "ok" });

    const created = await fetch(`${base}/items`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: "pnpm" }),
    });
    assert.equal(created.status, 201);
    assert.deepEqual(await created.json(), { id: 1, name: "pnpm" });

    const invalid = await fetch(`${base}/items`, { method: "POST" });
    assert.equal(invalid.status, 400);
  } finally {
    server.close();
  }
});
