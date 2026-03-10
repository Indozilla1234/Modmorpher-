# ModMorpher: Developer Migration Toolkit (Java to Bedrock)

**ModMorpher** is a high-performance pipeline designed for Java Edition developers to automate the migration of entity logic, models, and GeckoLib animations to the Minecraft Bedrock Edition (Add-on) schema.

---

## Technical Overview
This toolkit provides a structured workflow for original content creators who wish to maintain cross-platform parity for their mods. It eliminates the manual labor involved in rewriting entity behaviors and re-animating models from scratch.

### Core Capabilities
* **Bytecode Analysis:** Utilizes an integrated Java engine to analyze compiled `.jar` structures and map class hierarchies to Bedrock component-based data.
* **Animation Morphing:** Automatically translates Java-side animation triggers and vertex data into Bedrock `.animation.json` and state machine files.
* **Logic Mapping:** Provides a translation layer for NBT-based logic into Bedrock JSON-driven behavior schemas.

---

## Developer Workflow
ModMorpher is designed to fit into a standard local development environment.
Unfortunatly Modmorpher **ONLY SUPPORTS FORGE MODS THAT USE MCREATOR AND ARE 1.18+(with 1.12-1.17 results may vary)** however NeoForge support is coming soon!

### Prerequisites
* **Python 3.10+** (System Path)
* **OpenJDK 21+** (Required for the analysis engine)

### Execution Steps
1. Place the compiled Java `.jar` file into the project root directory.
2. Ensure the Java source or mappings are accessible if custom de-obfuscation is required.
3. Execute the pipeline manager via the terminal:
   ```bash
   python pipeline_manager.py

## Ethical Usage Policy
This toolkit is a bridge for creators, not a vehicle for piracy. 
* **Respect Creators:** Do not use this tool to port mods without the original author's explicit permission.
* **Support the Ecosystem:** Unauthorized redistribution of converted assets hurts the modding community and the creators you admire. 
* **Abuse Policy:** The maintainers of ModMorpher do not condone or support the use of this software for bypassing Marketplace protections or infringing on Intellectual Property.



## Why This License Exists

ModMorpher is designed to make cross‑platform modding fun, safe, and respectful.  
Because this toolkit touches both **Java Edition** and **Bedrock Edition** ecosystems, the license is intentionally structured to protect creators, communities, and the project itself.

### 🛡️ Protecting Java Creators  
Java mods are often open‑source, but they are also frequently stolen, reposted, or sold without permission.  
ModMorpher’s license ensures that:

- Java mod authors retain full control over their work  
- Mods can only be converted if you **own them or have explicit permission**  
- Converted content cannot be redistributed without the creator’s approval  

This keeps Java creators safe while still allowing players to enjoy their favorite mods with friends.

### 🧱 Protecting Bedrock Creators  
The Bedrock ecosystem includes DRM, Marketplace rules, and paid content.  
To avoid misuse and protect Bedrock creators:

- ModMorpher **does not bypass DRM**  
- Marketplace content **cannot** be converted  
- ARR and paid content are **strictly off‑limits**  

This ensures the tool is never used to harm Bedrock creators or violate Microsoft’s policies.

### 🔧 Protecting Mod Loaders and Communities  
Java loaders like Forge, Fabric, Quilt, and NeoForge rely on clear licensing and community trust.  
ModMorpher respects their rules by:

- Requiring permission for conversion  
- Preserving original licenses  
- Avoiding unauthorized forks or derivative works  

This prevents fragmentation or misuse that could harm the broader modding ecosystem.

### 👥 Protecting Players and Developers  
Most importantly, the license keeps ModMorpher fun and safe to use:

- You can convert **your own mods**  
- You can play with friends  
- You can explore, learn, and contribute  
- You can fork the project **privately** for personal development  
- You get a **10‑day grace period** to correct accidental violations  

The goal is to support creativity — not punish it.

### 🚀 Built for Fun, Not Abuse  
ModMorpher exists to help players enjoy the mods they love, not to enable piracy or harm creators.  
The license ensures the project stays alive, legal, and respectful of everyone’s work.

If you're a creator, player, or developer, this license is here to protect **you**, your content, and the community.


   
