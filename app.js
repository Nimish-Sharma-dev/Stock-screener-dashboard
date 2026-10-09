"use strict";
// The page only draws what the server pushes; all maths happens in Python.
const $ = (id) => document.getElementById(id);
const fmt = (v) => (v === null || v === undefined ? "n/a" : v.toFixed(2));

function badge(text, cls) {
  const s = document.createElement("span");
  s.className = "badge " + cls;
  s.textContent = text;
  return s;
}

function zClass(z) {
  if (z === null || z === undefined) return "";
  if (z < -2) return "z-buy";
  if (z < -1) return "z-neg";
  if (z > 2) return "z-high";
  if (z > 1) return "z-pos";
  return "";
}

function cell(text, cls) {
  const td = document.createElement("td");
  td.textContent = text;
  if (cls) td.className = cls;
  return td;
}

function render(v) {
  $("badges").replaceChildren(
    badge(v.live ? "LIVE" : "DAILY CLOSES ONLY", v.live ? "ok" : "warn"),
    badge(v.trade_enabled ? "TRADING ON (UAT)" : "VIEW ONLY", v.trade_enabled ? "warn" : "muted"),
    badge(v.order_placed ? "ORDER USED" : "NO ORDER YET", v.order_placed ? "warn" : "muted"),
    badge("stream: " + v.socket, "muted"),
  );
  $("title").textContent = v.title + "  -  " + v.time + " IST";

  const rows = [...v.rows].sort((a, b) => {
    if (a.z === null && b.z === null) return 0;
    if (a.z === null) return 1;
    if (b.z === null) return -1;
    return a.z - b.z;
  });
  $("rows").replaceChildren(...rows.map((r) => {
    const tr = document.createElement("tr");
    tr.append(cell(r.symbol), cell(fmt(r.close)), cell(fmt(r.mean)), cell(fmt(r.std)),
              cell(fmt(r.z), "z " + zClass(r.z)), cell(r.src), cell(r.reason));
    return tr;
  }));

  $("events").replaceChildren(...[...v.events].reverse().slice(0, 50).map((e) => {
    const li = document.createElement("li");
    li.textContent = `${e.ts} [${e.kind}] ${e.text}`;
    return li;
  }));
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (e) => render(JSON.parse(e.data));
  ws.onclose = () => {
    $("title").textContent = "Disconnected - retrying...";
    setTimeout(connect, 2000);
  };
}
connect();
