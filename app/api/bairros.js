// Casamento entre o bairro do anúncio e o polígono do mapa.
// Espelha scripts/geo/nomes.py: mudar a normalização lá exige mudar aqui.
import { readFileSync } from "node:fs";

const ABREVIACOES = {
  sta: "santa", sto: "santo", jd: "jardim", res: "residencial",
  cond: "condominio", pq: "parque", vl: "vila",
};

export function normalizar(nome) {
  if (!nome) return "";
  let s = nome.toLowerCase().normalize("NFD").replace(/\p{M}/gu, "")
    .replace(/[^a-z0-9]+/g, " ").trim();
  if (s.startsWith("bairro ")) s = s.slice("bairro ".length);
  return s.split(" ").map((p) => ABREVIACOES[p] ?? p).join(" ");
}

// GeoJSON gerado por scripts/geo/preparar_bairros.py; cada feature traz `chaves`
// (nome oficial + apelidos já normalizados).
export function carregarChaves(caminho) {
  const geo = JSON.parse(readFileSync(caminho, "utf-8"));
  const porChave = new Map();
  for (const f of geo.features) {
    for (const chave of f.properties.chaves) porChave.set(chave, f.properties);
  }
  return porChave;
}
