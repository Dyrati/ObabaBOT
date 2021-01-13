import re
import io
import json
import inspect
from . import utilities
from .utilities import command, DataTables, UserData, Namemaps, Text, reply


def getclass(name, djinncounts, item=None):
    name = name.lower()
    pcelements = {
        "isaac":"Venus", "garet":"Mars", "ivan":"Jupiter", "mia":"Mercury",
        "felix":"Venus", "jenna":"Mars", "sheba":"Jupiter", "piers":"Mercury"}
    elements = ["Venus", "Mercury", "Mars", "Jupiter"]
    relations = {   # Affinity, Weakness, Neutral, Primary
        'Venus':    ['Mars', 'Jupiter', 'Mercury', 'Venus'],
        'Mercury':  ['Jupiter', 'Mars', 'Venus', 'Mercury'],
        'Mars':     ['Venus', 'Mercury', 'Jupiter', 'Mars'],
        'Jupiter':  ['Mercury', 'Venus', 'Mars', 'Jupiter'],
    }
    element = pcelements[name]
    elevels = [cnt+5 if e == element else cnt for e,cnt in zip(elements, djinncounts)]
    if item:
        item = item.lower()
        aliases = {
            "card": "mysterious card", "mc": "mysterious card",
            "whip": "trainer's whip", "tw": "trainer's whip",
            "tome": "tomegathericon", "tm": "tomegathericon",
        }
        item = aliases.get(item, item)
        assert item in ("mysterious card", "trainer's whip", "tomegathericon"), \
            f"\"{item}\" not recognized"
        table = item
    elif sum(elevels) == elevels[elements.index(element)]:  # if all djinn match pc element
        if name in ("jenna", "piers"):
            table = "primary2"
        else:
            table = "primary1"
    else:
        sort1 = {e:elevels[elements.index(e)] for e in relations[element]}  # sort by relation
        sort2 = sorted(sort1.items(), key=lambda x: x[1])  # sort by elevel
        dominance = [x[0] for x in reversed(sort2)] # highest priority to lowest
        if relations[element][0] in dominance[:2]:  # if affinity element is 1st or 2nd dominant
            if element in ("Venus", "Mars"):
                table = "earth/fire"
            elif element in ("Mercury", "Jupiter"):
                table = "wind/water"
        else:  # go to table of 2nd dominant
            table = ("earth", "water", "fire", "wind")[elements.index(dominance[1])]
    classtables = [
        "primary1", "water", "wind", "earth", "fire", "earth/fire", "wind/water",
        "primary2", "mysterious card", "trainer's whip", "tomegathericon"]
    offsets = [1,40,70,100,130,160,180,200,220,230,240,244]  # ID locations of class tables
    tableID = classtables.index(table)
    bestmatch = 0
    for i in range(offsets[tableID], offsets[tableID+1]):
        classdata = DataTables["classdata"][i]
        if classdata["name"] == "?": continue
        requirement = (classdata[e] for e in elements)
        if all(e1 >= e2 for e1, e2 in zip(elevels, requirement)):
            bestmatch = i
    return DataTables['classdata'][bestmatch]


def damage(
        abilityname, ATK=None, POW=None, target=None,
        HP=None, DEF=None, RES=None, RANGE=None):
    abilityname = abilityname.lower()
    elements = ["Venus", "Mercury", "Mars", "Jupiter"]
    ability = Namemaps["abilitydata"][abilityname][0]
    if target:
        enemy = Namemaps["enemydata"][target][0]
        if HP is None: HP = enemy["HP"]
        if DEF is None: DEF = enemy["DEF"]
        estats = DataTables["elementdata"][enemy["elemental_stats_id"]]
        if RES is None: RES = estats.get(ability["element"] + "_Res")
    damage_type = ability["damage_type"]
    if damage_type == "Healing":
        damage = ability["power"]*POW/100
    elif damage_type == "Added Damage":
        damage = (ATK-DEF)/2 + ability["power"]
        if ability["element"] != "Neutral":
            damage *= 1 + (POW-RES)/400
    elif damage_type == "Multiplier":
        damage = (ATK-DEF)/2*ability["power"]/10
        if ability["element"] != "Neutral":
            damage *= 1 + (POW-RES)/400
    elif damage_type == "Base Damage":
        damage = ability["power"]*(1 + (POW-RES)/200)
        if RANGE: damage *= [1, .8, .6, .4, .2, .1][RANGE]
    elif damage_type == "Base Damage (Diminishing)":
        damage = ability["power"]*(1 + (POW-RES)/200)
        if RANGE: damage *= [1, .5, .3, .1, .1, .1][RANGE]
    elif damage_type == "Summon":
        summon = Namemaps["summondata"][abilityname][0]
        damage = summon["power"] + summon["hp_multiplier"]*min(10000, HP)
        damage *= (1 + (POW-RES)/200)
        if RANGE: damage *= [1, .7, .4, .3, .2, .1][RANGE]
    if int(damage) == damage: damage = int(damage)
    return damage


def roomname(gamenumber, mapnumber, doornumber):
    roomtable = DataTables[f"room_references{gamenumber}"]
    mapdata = DataTables[f"mapdata{gamenumber}"]
    for r in roomtable:
        door, check = r["door"], r["room_or_area"]
        flag, door = door & 0x8000, door & 0x7FFF
        area = mapdata[mapnumber]["area"]
        if (check==mapnumber if flag else check==area):
            if door in (0x7fff, doornumber): return r["name"]
    return roomtable[0]["name"]


build_dates = {
    0x1C85: "Golden Sun - The Lost Age (UE)",
    0x1D97: "Golden Sun - The Lost Age (G)",
    0x1DC7: "Golden Sun - The Lost Age (S)",
    0x1D98: "Golden Sun - The Lost Age (F)",
    0x1DC8: "Golden Sun - The Lost Age (I)",
    0x198A: "Golden Sun - The Lost Age (J)",
    0x1652: "Golden Sun (UE)",
    0x1849: "Golden Sun (G)",
    0x1885: "Golden Sun (S)",
    0x1713: "Golden Sun (F)",
    0x1886: "Golden Sun (I)",
    0x159C: "Golden Sun (J)",}

def readsav(data):
    f = io.BytesIO(data)
    def read(size):
        return int.from_bytes(f.read(size), "little")
    headers = []
    for i in range(16):
        f.seek(0x1000*i)
        headers.append({
            "addr": 0x1000*i,
            "header": f.read(7),
            "slot": read(1),
            "checksum": read(2),
            "priority": read(2),
        })
    valid_saves = [h for h in headers if h["header"] == b"CAMELOT" and h["slot"] < 0xF]
    slots = {}
    for save in valid_saves:
        if save["priority"] > slots.get(save["slot"], -1):
            slots[save["slot"]] = save
    filedata = []
    for i in range(3):
        if not slots.get(i): continue
        f.seek(slots[i]["addr"] + 0x10)
        data = f.read(0x2FF0)
        read = lambda addr, size: int.from_bytes(data[addr:addr+size], "little")
        version = build_dates[read(0x26, 2) & ~0x8000]
        if "The Lost Age" in version: GAME = 2; offset = 0x20
        else: GAME = 1; offset = 0
        party_size = sum((1 if read(0x40, 1) & 2**j else 0 for j in range(8)))
        positions = [read(0x438+offset + j, 1) for j in range(party_size)]
        addresses = [0x500+offset + 0x14C*p for p in positions]
        filedata.append({
            "version": version,
            "slot": i,
            "party_members": read(0x40, 1),
            "framecount": read(0x244, 4),
            "summons": read(0x24C, 4),
            "coins": read(0x250, 4),
            "map_number": read(0x400+offset, 2),
            "door_number": read(0x402+offset, 2),
            "leader": read(0x434+offset, 1),
            "party_positions": positions,
            "party": [{
                "name": [read(base+j, 1) for j in range(15)],
                "level": read(base+0xF, 1),
                "element": [0,2,3,1,0,2,3,1][p],
                "base_stats": {
                    "HP": read(base+0x10, 2),
                    "PP": read(base+0x12, 2),
                    "ATK": read(base+0x18, 2),
                    "DEF": read(base+0x1A, 2),
                    "AGI": read(base+0x1C, 2),
                    "LCK": read(base+0x1E, 1),
                    "venus_pow": read(base+0x24, 2),
                    "venus_res": read(base+0x26, 2),
                    "merc_pow": read(base+0x28, 2),
                    "merc_res": read(base+0x2A, 2),
                    "mars_pow": read(base+0x2C, 2),
                    "mars_res": read(base+0x2E, 2),
                    "jup_pow": read(base+0x30, 2),
                    "jup_res": read(base+0x32, 2),
                },
                "stats": {
                    "HP_max": read(base+0x34, 2),
                    "PP_max": read(base+0x36, 2),
                    "HP_cur": read(base+0x38, 2),
                    "PP_cur": read(base+0x3A, 2),
                    "ATK": read(base+0x3c, 2),
                    "DEF": read(base+0x3e, 2),
                    "AGI": read(base+0x40, 2),
                    "LCK": read(base+0x42, 1),
                    "ven_pow": read(base+0x48, 2),
                    "ven_res": read(base+0x4a, 2),
                    "merc_pow": read(base+0x4c, 2),
                    "merc_res": read(base+0x4e, 2),
                    "mars_pow": read(base+0x50, 2),
                    "mars_res": read(base+0x52, 2),
                    "jup_pow": read(base+0x54, 2),
                    "jup_res": read(base+0x56, 2),
                },
                "abilities": [read(base+0x58+4*j, 4) for j in range(32)],
                "inventory": [read(base+0xD8+2*j, 2) for j in range(15)],
                "djinn": [read(base+0xF8+4*j, 4) for j in range(4)],
                "set_djinn": [read(base+0x108+4*j, 4) for j in range(4)],
                "djinncounts": [read(base+0x118+j, 1) for j in range(4)],
                "set_djinncounts": [read(base+0x11C+j, 1) for j in range(4)],
                "exp": read(base+0x124, 4),
                "class": read(base+0x129, 1),
            } for p,base in zip(positions, addresses)],
        })
    partysummons = 0
    partydjinn = 0
    display = []
    for f in filedata:
        f["party_members"] = [Text["pcnames"][i] for i in range(8) if f["party_members"] & 2**i]
        f["summons"] = [DataTables["summondata"][i]["name"] for i in range(33) if f["summons"] & 2**i]
        f["area"] = roomname(GAME, f["map_number"], f["door_number"])
        djinncounts = [0, 0, 0, 0]
        for pc in f["party"]:
            pc["name"] = "".join([chr(c) for c in pc["name"] if c])
            pc["element"] = Text["elements"][pc["element"]]
            pc["abilities"] = [Text["abilities"][i & 0x3FF] for i in pc["abilities"] if i & 0x3FF]
            pc["inventory"] = {Text["items"][i & 0x1FF]: i for i in pc["inventory"] if i & 0x1FF}
            for k, v in pc["inventory"].items():
                metadata = [(v>>11 & 0x1F) + 1]
                if v & 1<<9: metadata.append("equipped")
                if v & 1<<10: metadata.append("broken")
                pc["inventory"][k] = metadata
            for i, count in enumerate(pc["djinncounts"]):
                djinncounts[i] += count
            pc["class"] = Text["classes"][pc["class"]]
            pc["djinn"] = sum((d<<20*i for i,d in enumerate(pc["djinn"])))
            pc["set_djinn"] = sum((d<<20*i for i,d in enumerate(pc["set_djinn"])))
            pc["djinn"] = [Text["djinn"][i] for i in range(80) if pc["djinn"] & 2**i]
            pc["set_djinn"] = [Text["djinn"][i] for i in range(80) if pc["set_djinn"] & 2**i]
            pc["elevels"] = pc["set_djinncounts"].copy()
            for i in range(4):
                if Text["elements"][i] == pc["element"]: pc["elevels"][i] += 5
        seconds, minutes, hours = (f["framecount"]//60**i for i in range(1,4))
        seconds %= 60; minutes %= 60
        f["playtime"] = "{:02}:{:02}:{:02}".format(hours, minutes, seconds),
        for p, pc in zip(positions, f["party"]):
            if p == f["leader"]: f["leader"] = pc["name"]; break
        f["djinncounts"] = djinncounts
    return filedata


def preview(data):
    filedata = readsav(data)
    pages = {}
    slots = []
    used_slots = [f["slot"] for f in filedata]
    preview = utilities.Charmap()
    preview.addtext(filedata[0]["version"], (0,0))
    leaders, areas = [], []
    maxname = max((len(f["leader"]) for f in filedata))
    maxarea = max((len(f["area"]) for f in filedata))
    for i in range(3):
        if i not in used_slots:
            preview.addtext(f"{i}  {'':-<{maxname}}  {'':-<{maxarea}}", (0, 2+i))
        else:
            f = next(filter(lambda x: x["slot"]==i, filedata))
            preview.addtext(f"{i}  {f['leader']:<{maxname}}  {f['area']:<{maxarea}}", (0, 2+i))
    for f in filedata:
        slot = {}
        slot["slot"] = f["slot"]
        slot["time"] = f["playtime"]
        slot["coins"] = f["coins"]
        slot["djinn"] = [f["djinncounts"]]
        slot[""] = ""
        maxlen = max(len(str(f["djinncounts"])), *(len(pc["name"])+4 for pc in f["party"]))
        slot["PCs"] = [f"{pc['name']:<{maxlen-4}}{pc['level']:>4}" for pc in f["party"]]
        slots.append(slot)
    preview.addtext(utilities.tableV(slots), (0,6))
    pages["preview"] = f"```\n{preview}\n```"
    pages["help"] = inspect.cleandoc("""```
        Click emotes to view other pages of this message

        P     - Go to preview page
        0,1,2 - Select a save slot
        <,>   - Scroll through characters of current save slot
        ?     - Show this help page
        ```""")
    for f in filedata:
        slot = f["slot"]
        pages[slot] = []
        for pc in f["party"]:
            out = utilities.Charmap()
            out.addtext(pc["name"], (0, 0))[0]
            out.addtext(pc["class"], (0, 1))[0]
            out.addtext(utilities.dictstr({"LV": pc["level"], "EXP": pc["exp"]}), (14,0))
            base = pc["base_stats"]
            stats = pc["stats"]
            out.addtext("Stats", (0, 3))
            x,y = out.addtext(utilities.dictstr({
                "HP": f"{stats['HP_cur']}/{stats['HP_max']}",
                "PP": f"{stats['PP_cur']}/{stats['PP_max']}",
                "ATK": stats["ATK"]}, sep=" "), (0, 4))
            x,y = out.addtext(utilities.dictstr({
                "DEF": stats["DEF"],
                "AGI": stats["AGI"],
                "LCK": stats["LCK"]}, sep=" "), (x+2, 4))
            out.addtext("Base Stats", (x+3, 3))
            x,y = out.addtext(utilities.dictstr({
                "HP": base['HP'],
                "PP": base['PP'],
                "ATK": base["ATK"]}, sep=" "), (x+3, 4))
            x,y = out.addtext(utilities.dictstr({
                "DEF": base["DEF"],
                "AGI": base["AGI"],
                "LCK": base["LCK"]}, sep=" "), (x+2, 4))
            elementdata = []
            for i, name in enumerate(["ven", "merc", "mars", "jup"]):
                elementdata.append(
                    {"Estats": name.title(),
                    "Djinn": f"{pc['set_djinncounts'][i]}/{pc['djinncounts'][i]}",
                    "Level": pc["elevels"][i],
                    "Power": pc["stats"][f"{name}_pow"],
                    "Resist": pc["stats"][f"{name}_res"]})
            out.addtext(utilities.tableV(elementdata), (x+3,2))
            out.addtext("Items", (0, 8))
            inventory = []
            for k,v in pc["inventory"].items():
                state = "B" if "broken" in v[1:] else "E" if "equipped" in v[1:] else "-"
                inventory.append({"item": k+" ", "amt": v[0], "state": state})
            x = -1
            ymax = 0
            for i in range(0, len(inventory), 5):
                x,y = out.addtext(utilities.tableH(inventory[i:i+5], headers=False), (x+3, 9))
                ymax = max(ymax, y)
            out.addtext("Djinn", (0, ymax+1))
            djinn = []
            for d in pc["djinn"]:
                djinn.append({"name": d, "state": "√" if d in pc["set_djinn"] else "-"})
            x,_ = out.addtext(utilities.tableH(djinn, headers=False), (2,ymax+2))
            x = max(x, 4)
            out.addtext("Abilities", (x+3, ymax+1))
            x += 2
            if pc["abilities"]:
                height = max(len(pc["abilities"])/4, len(pc["djinn"]))
                height = int(height) + 1 if height != int(height) else int(height)
                for i in range(0, len(pc["abilities"]), height):
                    x,_ = out.addtext("\n".join(pc["abilities"][i:i+height]), (x+3, ymax+2))
            pages[slot].append(f"```\n{out}\n```")
    return pages