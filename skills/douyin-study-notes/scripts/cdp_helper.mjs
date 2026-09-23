#!/usr/bin/env node

const [action, portText] = process.argv.slice(2);
const port = Number(portText);

if (!action || !Number.isInteger(port)) {
  process.stderr.write("Usage: node cdp_helper.mjs <capture|close> <port>\n");
  process.exit(2);
}

async function endpoint(path) {
  const response = await fetch(`http://127.0.0.1:${port}${path}`);
  if (!response.ok) throw new Error(`CDP endpoint returned ${response.status}`);
  return response.json();
}

async function command(wsUrl, method, params = {}) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(wsUrl);
    const timer = setTimeout(() => {
      socket.close();
      reject(new Error(`Timed out waiting for ${method}`));
    }, 10000);
    socket.addEventListener("open", () => {
      socket.send(JSON.stringify({ id: 1, method, params }));
    });
    socket.addEventListener("message", (event) => {
      const payload = JSON.parse(String(event.data));
      if (payload.id !== 1) return;
      clearTimeout(timer);
      socket.close();
      if (payload.error) reject(new Error(payload.error.message));
      else resolve(payload.result || {});
    });
    socket.addEventListener("error", () => {
      clearTimeout(timer);
      reject(new Error(`WebSocket failed for ${method}`));
    });
  });
}

if (action === "capture") {
  const targets = await endpoint("/json/list");
  const page = targets.find((item) => item.type === "page" && item.webSocketDebuggerUrl);
  if (!page) throw new Error("No debuggable page target found");
  const expression = `JSON.stringify({title: document.title, url: location.href, text: document.body ? document.body.innerText : ""})`;
  const result = await command(page.webSocketDebuggerUrl, "Runtime.evaluate", {
    expression,
    returnByValue: true,
  });
  process.stdout.write(result.result?.value || "{}");
} else if (action === "close") {
  const version = await endpoint("/json/version");
  await command(version.webSocketDebuggerUrl, "Browser.close");
} else {
  throw new Error(`Unknown action: ${action}`);
}
