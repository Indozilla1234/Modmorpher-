# ModMorpher - Java → Bedrock migration thing

⚠️ Heads up: this script will auto-install Python packages (`javalang`, `Pillow`, etc) the first time you run it. It’s annoying, but it’s required.

ModMorpher tries to take a Minecraft Java mod and spit out a Bedrock add-on (`.mcaddon`). It’s not perfect, sometimes it borks things, but it usually gets you close enough to tweak manually.

---

## what it does (sorta)
- reads Java class/source/jar stuff and makes a best guess at Bedrock / component equivalents
- converts GeckoLib animation ids into Bedrock `.animation.json` + controller stubs
- extracts textures/models/sounds from the jar into a Bedrock pack
- tries to “translate” common NBT/logic patterns, but it’s not magic
- custom logic thingys to the Bedrock Scripting API

---

## what works best
This is made for **MCreator mods built with Forge / NeoForge**.

| Minecraft | loader | how reliable it is |
|---|---|---|
| 1.20.1+ | NeoForge | decent, but expect some manual fixing |
| 1.18+ | Forge | best chance |
| 1.12+ | Forge | will probably need manual fixes |
| 1.3+ | Forge | not really worth it |
| 1.20.1+ | Fabric / Quilt | not worth it, kinda have support not, but still would NOT RECOMEND

> Hand-made mods can sometimes work, but you’ll often end up having to fix things by hand.

---

## requirements
- Python 3.10+ on your PATH
- OpenJDK 21+ (needed for the decompiler)

---

## quick run
1. Put your compiled `.jar` in this folder (project root).
2. Run:
   ```bash
   python modmorpher.py
   ```
3. When it's done, you should have `Bedrock_Pack.mcaddon` in this folder.

There will also be a `Bedrock_Pack/` folder with the raw pack structure if you want to poke around.

---

## keep in mind
- It installs deps automatically. If it crashes the first time, try running it again.
- It won’t convert everything. Complex AI, special animations, and weird NBT stuff usually need manual fixing.
- Treat the output as a starting point, not a finished pack.
- If it “fails silently”, check the terminal output — it usually gives a clue.

---

## please don’t
- use this to rip/redistribute paid or Marketplace content(IDK HOW YOU WOULD EVEN)
- convert mods you don’t own or don’t have permission to convert
- expect it to bypass DRM (it doesn’t, and can't)

---

## why the license stuff is here
This project is meant to help mod creators & players, not to wreck people’s work.
If you’re converting someone else’s mod, make sure you have permission.
If it’s Marketplace/paid content, don’t.

---

That’s it. It’s a messy tool that tries to do a lot. If it breaks, blame Minecraft Bedrock and maybe the spacetime continuum. ;)


   
