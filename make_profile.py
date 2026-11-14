"""Builds a Throne route profile with the same rules as the Cudy router.

Usage: python make_profile.py <router config.json> <out.json>

The router's live sing-box config is the source, so re-running this after
changing site lists on the router gives Throne the same rules.
"""
import json
import sys

GEOSITE_RU = "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-category-ru.srs"
GEOIP_RU = "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/geoip-ru.srs"

# Router-only outbounds that Throne does not have. ElevenLabs uses a second
# subscription on the router; on a PC it goes through the PC's own proxy.
OUTBOUND_MAP = {"proxy": "proxy", "direct": "direct", "eleven": "proxy"}
FIELDS = ("domain", "domain_suffix", "domain_keyword", "domain_regex", "ip_cidr",
          "protocol", "network", "port", "ip_is_private")


def name_for(rule, out):
    ds = rule.get("domain_suffix", [])
    kw = rule.get("domain_keyword", [])
    if rule.get("protocol") == ["bittorrent"] or rule.get("protocol") == "bittorrent":
        return "Торренты напрямую"
    if rule.get("ip_is_private"):
        return "Локальная сеть напрямую"
    if "user-direct.invalid" in ds:
        return "Мои сайты: напрямую"
    if "user-proxy.invalid" in ds:
        return "Мои сайты: через VPN"
    if "elevenlabs.io" in ds:
        return "ElevenLabs"
    if "twitch.tv" in ds:
        return "Twitch напрямую"
    if "spotify" in kw:
        return "Spotify через VPN"
    if "play.google.com" in ds:
        return "Google Play через VPN"
    if "rule_set" in rule:
        return "Российские сайты и IP напрямую"
    if "ru" in ds:
        return "Домены .ru .su .рф напрямую"
    if rule.get("network") == "udp" and rule.get("port") == 443:
        return "Блок QUIC (ускоряет загрузки)"
    return f"rule ({out})"


GS = "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/{}.srs"

# PC-only additions on top of the router rules. Process rules need Throne's TUN mode.
APP_DIRECT = {
    "name": "Торрент-клиенты напрямую",
    "process_name": ["qbittorrent.exe", "utorrent.exe", "BitTorrent.exe", "transmission-qt.exe",
                     "tixati.exe", "Motrix.exe", "fdm.exe"],
    "outbound": "direct",
}
APP_PROXY = {
    "name": "Программы через VPN",
    "process_name": [
        "Discord.exe", "DiscordPTB.exe", "DiscordCanary.exe",
        "Telegram.exe", "AyuGram.exe", "Kotatogram.exe",
        "Spotify.exe",
        "EADesktop.exe", "EABackgroundService.exe", "EALauncher.exe", "Origin.exe",
        "ChatGPT.exe", "Claude.exe", "Perplexity.exe", "Cursor.exe", "Windsurf.exe",
        "WhatsApp.exe", "Signal.exe", "Instagram.exe",
        "Notion.exe", "Figma.exe",
    ],
    "outbound": "proxy",
}
# Must sit above the Russian rule-sets: their CDNs often have caches inside
# Russian networks, so geoip-ru would otherwise send them direct (and slowed).
SERVICES_PROXY = [
    {"name": "YouTube через VPN", "rule_set": [GS.format("geosite-youtube")], "outbound": "proxy"},
    {"name": "Discord через VPN", "rule_set": [GS.format("geosite-discord")], "outbound": "proxy"},
    {"name": "Telegram через VPN", "rule_set": [GS.format("geosite-telegram")],
     "ip_cidr": ["91.108.4.0/22", "91.108.8.0/22", "91.108.12.0/22", "91.108.16.0/22",
                 "91.108.20.0/22", "91.108.56.0/22", "95.161.64.0/20", "149.154.160.0/20",
                 "185.76.151.0/24"], "outbound": "proxy"},
    {"name": "Нейросети через VPN", "rule_set": [GS.format("geosite-openai"), GS.format("geosite-anthropic"),
                                                  GS.format("geosite-category-ai-!cn")], "outbound": "proxy"},
    {"name": "Соцсети через VPN", "rule_set": [GS.format("geosite-instagram"), GS.format("geosite-facebook"),
                                                GS.format("geosite-twitter"), GS.format("geosite-linkedin"),
                                                GS.format("geosite-tiktok")], "outbound": "proxy"},
]
RU_SERVICES_DIRECT = [
    {"name": "Яндекс, VK, Mail.ru напрямую",
     "rule_set": [GS.format("geosite-yandex"), GS.format("geosite-vk"), GS.format("geosite-mailru")],
     "outbound": "direct"},
    {"name": "Загрузки Steam напрямую",
     "domain_suffix": ["steamcontent.com", "steamserver.net", "steampipe.akamaized.net", "steamcdn-a.akamaihd.net"],
     "outbound": "direct"},
]


def extra(rule):
    out = {"type": "custom", **{k: v for k, v in rule.items() if k != "name"}, "action": "route"}
    out["name"] = rule["name"]
    return out


def arrange(router_rules):
    """Puts the PC additions between the router rules in a sensible order."""
    head, mine, apps_tail, ru_tail = [], [], [], []
    for r in router_rules:
        n = r["name"]
        if n in ("Торренты напрямую", "Локальная сеть напрямую"):
            head.append(r)
        elif n.startswith("Мои сайты") or n == "ElevenLabs":
            mine.append(r)
        elif n.startswith(("Российские", "Домены", "Блок QUIC")):
            ru_tail.append(r)
        else:
            apps_tail.append(r)  # Twitch, Spotify, Google Play
    return (head + [extra(APP_DIRECT)] + mine + [extra(APP_PROXY)]
            + [extra(s) for s in SERVICES_PROXY] + apps_tail
            + [extra(s) for s in RU_SERVICES_DIRECT] + ru_tail)


def convert(cfg):
    server_ips = {f"{o.get('server')}/32" for o in cfg.get("outbounds", []) if o.get("server")}
    rules = []
    for r in cfg["route"]["rules"]:
        action = r.get("action", "route")
        if action in ("sniff", "hijack-dns"):
            continue  # Throne adds these itself
        if r.get("ip_cidr") and set(r["ip_cidr"]) <= server_ips:
            continue  # router's own VPN server address
        out = {"type": "custom"}
        for f in FIELDS:
            if f in r:
                v = r[f]
                if f == "domain_suffix":
                    v = [d for d in v if not d.endswith(".invalid")]
                    if not v:
                        continue
                if f == "port" and not isinstance(v, list):
                    v = [v]
                if f == "protocol" and not isinstance(v, list):
                    v = [v]
                out[f] = v
        if "rule_set" in r:
            out["rule_set"] = [GEOSITE_RU if "geosite" in t else GEOIP_RU for t in r["rule_set"]]
        if action == "reject":
            out["action"] = "reject"
        else:
            out["action"] = "route"
            out["outbound"] = OUTBOUND_MAP.get(r.get("outbound"), "proxy")
        if not any(k in out for k in FIELDS + ("rule_set",)):
            continue  # an empty user list
        out["name"] = name_for(r, out.get("outbound", "block"))
        rules.append(out)
    return {
        "kind": "throne-route-profile",
        "v": 1,
        "name": "Как дома (Cudy)",
        "default_outbound": "proxy",
        "rules": arrange(rules),
    }


if __name__ == "__main__":
    cfg = json.load(open(sys.argv[1], encoding="utf-8"))
    prof = convert(cfg)
    json.dump(prof, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    for r in prof["rules"]:
        print(f"{r['name']}: {r.get('outbound', r['action'])}")
