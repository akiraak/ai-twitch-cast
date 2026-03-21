# Native Windows Rendering for Streaming (Without Browser Engine)

## Research: 2026-03-14

## Background

The current system uses Electron to render `broadcast.html` (Three.js + three-vrm + CSS overlays + audio), then pipes frames to FFmpeg for RTMP streaming. This research investigates replacing the browser engine entirely with native Windows rendering.

---

## 1. VRM Model Rendering Natively on Windows

### VRM Format Overview

VRM is a file format for 3D humanoid avatars based on **glTF 2.0**. It extends glTF with:
- **Humanoid bone mappings** (standardized skeleton)
- **BlendShape groups** (facial expressions mapped to morph targets)
- **SpringBone** (physics simulation for hair/clothing)
- **MToon shader** (anime-style toon shading)
- **First-person settings** (head visibility control)
- **Metadata/licensing**

VRM 0.x and VRM 1.0 have different JSON extension schemas.

### C++ VRM Libraries

| Library | Language | Features | Status |
|---------|----------|----------|--------|
| **[VRM.h](https://github.com/infosia/VRM.h)** | C++ header-only | VRM 0.x + 1.0 parsing/serialization, SpringBone/MToon/NodeConstraint extensions | Active, MIT |
| **[tinygltf](https://github.com/syoyo/tinygltf)** | C++ header-only | glTF 2.0 loading (recognizes .vrm extension), skinning, morph targets | Stable/maintenance |
| **[Assimp](https://github.com/assimp/assimp)** | C++ | glTF 2.0 import with .vrm recognition, morph targets, skinning | Active |
| **[fx-gltf](https://github.com/jessey-git/fx-gltf)** | C++ | glTF 2.0 binary loader (used by VRM.h) | Stable |

**Key insight**: VRM.h handles VRM-specific extensions (BlendShape, SpringBone, MToon metadata) while tinygltf/Assimp handle the underlying glTF mesh/skeleton/animation data. You need **both** -- a glTF loader for geometry + a VRM parser for the VRM extensions.

### .NET VRM Libraries

| Library | Language | Features | Status |
|---------|----------|----------|--------|
| **[SharpGLTF](https://github.com/vpenades/SharpGLTF)** | C# .NET | glTF 2.0 read/write, skinning, morph targets, animation runtime | Active |
| **[UniVRM](https://github.com/vrm-c/UniVRM)** | C# (Unity) | Complete VRM implementation, but **Unity-dependent** | Active |

SharpGLTF is the most promising .NET option for non-Unity VRM loading. It provides `SceneTemplate` and `SceneInstance` for runtime animation evaluation including skinning and morph targets.

### Game Engine Approaches

| Engine | VRM Support | Headless/Offscreen | Notes |
|--------|------------|-------------------|-------|
| **Godot 4.x** | [godot-vrm](https://github.com/V-Sekai/godot-vrm) addon: VRM 0.0 + 1.0, MToon, SpringBone, BlendShape | **No true offscreen rendering** yet (proposal #5790). `--headless` disables all rendering. | VRM support is complete but offscreen rendering is blocked |
| **Unity** | UniVRM: complete VRM implementation | Headless mode exists but no rendering. Render-to-texture possible in builds. | Requires Unity license for commercial use |
| **Unreal Engine** | [VRM4U](https://github.com/ruyo/VRM4U): VRM 0.x + 1.0, MToon, SpringBone | Headless rendering possible | Heavy, complex integration |
| **Stride Engine** | No native VRM. glTF runtime loading possible | Headless discussion ongoing | Open-source C# engine, .NET Foundation project |

### Native 3D Rendering Engines (No Game Engine)

| Engine | Language | APIs | glTF | Offscreen | Notes |
|--------|----------|------|------|-----------|-------|
| **[Filament](https://github.com/google/filament)** | C++ | Vulkan, OpenGL, Metal | Yes (built-in loader) | Yes | Google's PBR engine. Small footprint. No VRM-specific support but could add MToon shader. |
| **[bgfx](https://github.com/bkaradzic/bgfx)** | C++ | D3D9-12, OpenGL, Vulkan, Metal | Yes (converter tool) | Yes | "Bring your own engine" style. Very mature. |
| **[Diligent Engine](https://github.com/DiligentGraphics/DiligentEngine)** | C++ | D3D11, D3D12, Vulkan, OpenGL | Yes (asset loader) | Likely | Modern graphics API abstraction |
| **[Magnum](https://github.com/mosra/magnum)** | C++ | OpenGL, Vulkan | Yes (via tinygltf) | Yes | Lightweight, modular |
| **[Silk.NET](https://github.com/dotnet/Silk.NET)** | C# .NET | D3D11/12, Vulkan, OpenGL | Via Assimp bindings | Yes | .NET Foundation project, low-level bindings |
| **[Veldrid](https://github.com/veldrid/veldrid)** | C# .NET | D3D11, Vulkan, Metal, OpenGL | Custom loader needed | **Yes (explicitly supported)** | Can run without window for GPU operations |

### VRM Animation & BlendShape in Native

**BlendShape (Morph Target) control** is standard in glTF 2.0:
- Each mesh can have morph targets with position/normal deltas
- Morph weights (0.0-1.0) are applied per-target
- VRM maps named expressions (Joy, Angry, Blink, etc.) to sets of morph target weights
- In native code: load morph targets via glTF loader, apply weights via VRM extension data

**SpringBone physics** uses Verlet integration:
- Chain of joints connected by springs
- Parameters: stiffness, gravity, drag, collision radius
- Colliders (sphere/capsule) for collision detection
- VRM4U (Unreal) has a complete C++ implementation that could be referenced
- The [babylon-vrm-loader](https://github.com/virtual-cast/babylon-vrm-loader) has a TypeScript SpringBone implementation that's readable

**Idle animation** is just sine-wave bone rotation applied per-frame -- trivial to implement in any language.

### MToon Shader (Critical for VRM Look)

MToon is the toon shader that gives VRM models their anime look. Key properties:
- **Lit/Shade interpolation**: `dot(normal, lightDir)` with configurable threshold (`shadingShiftFactor`) and feather width (`shadingToonyFactor`)
- **Outline rendering**: vertex extrusion along normals (worldCoordinates or screenCoordinates mode)
- **Rim lighting**: parametric or matcap-based
- **UV animation**: scroll/rotation for effects
- **Emissive**: HDR emissive multiplier

Reimplementing MToon in HLSL/GLSL is **feasible** -- the [VRM specification](https://github.com/vrm-c/vrm-specification/blob/master/specification/VRMC_materials_mtoon-1.0/README.md) documents all parameters. Reference implementations exist in:
- three-vrm (GLSL, in `packages/three-vrm-materials-mtoon/src/shaders/`)
- godot-vrm (Godot shader language)
- UniVRM (Unity ShaderLab/HLSL)
- VRM4U (Unreal material system)

---

## 2. 2D Overlay Rendering Natively

### Direct2D + DirectWrite (Windows Native)

**Best option for Windows-native 2D overlays on top of 3D.**

Microsoft's Direct2D interoperates directly with Direct3D via DXGI surfaces:
1. Render 3D scene to a D3D11 render target
2. Obtain `IDXGISurface` from the render target
3. Create `ID2D1RenderTarget` from the DXGI surface via `CreateDxgiSurfaceRenderTarget()`
4. Draw 2D content (text, rectangles, gradients) on top of the 3D scene
5. Present or read back the composited result

Features:
- **DirectWrite**: High-quality text rendering (ClearType, subpixel), custom fonts, text layout
- **Direct2D**: Rectangles, rounded rects, gradients, opacity, transforms, clipping
- **Hardware accelerated** when on top of Direct3D
- **No external dependencies** -- built into Windows

This can replicate all CSS-styled panels (TODO list, activity log, subtitles) with:
- `FillRoundedRectangle()` for panel backgrounds
- `DrawText()` / `DrawTextLayout()` for text content
- Semi-transparent brushes for glass effects
- Clip regions for scrolling text

### SkiaSharp (.NET Alternative)

If using .NET (C#), SkiaSharp provides similar capabilities:
- Cross-platform (wraps Google Skia)
- GPU accelerated on Windows
- Text, shapes, gradients, images, blending
- Can render to `SKSurface` backed by GPU texture

### Compositing Approach

For a native app, the rendering order would be:
1. Clear render target
2. Draw background image/color
3. Render 3D VRM avatar
4. Render window capture images as textured quads
5. Render 2D overlays (panels, text, subtitles) via Direct2D on the same surface

---

## 3. Offscreen Rendering Pipeline for Streaming

### DirectX 11 Render-to-Texture

1. Create `ID3D11Texture2D` with `D3D11_BIND_RENDER_TARGET` flag
2. Create `ID3D11RenderTargetView` from the texture
3. Render 3D + 2D content to this render target (no window needed)
4. For readback: create a **staging texture** (`D3D11_USAGE_STAGING`, `D3D11_CPU_ACCESS_READ`)
5. `CopyResource()` from render target to staging texture
6. `Map()` the staging texture to get CPU-accessible pixel data

**Performance considerations**:
- **Double-buffer staging textures** to avoid GPU pipeline stalls
- Copy to staging texture N while reading from staging texture N-1
- At 1080p30, each frame is ~8MB (BGRA) -- readback takes <1ms with proper double-buffering

### GPU-to-FFmpeg Pipeline Options

**Option A: CPU pipe to FFmpeg process (simplest)**
```
GPU render -> staging texture -> Map() -> memcpy to pipe -> FFmpeg stdin -> RTMP
```
- FFmpeg launched as child process with `-f rawvideo -pix_fmt bgra -s 1920x1080 -r 30 -i pipe:0`
- Simple, reliable, well-understood
- CPU cost: memcpy + FFmpeg software encoding (or use `-c:v h264_nvenc` for GPU encoding)

**Option B: FFmpeg libav API integration (more efficient)**
```
GPU render -> staging texture -> Map() -> AVFrame -> avcodec_send_frame() -> RTMP
```
- Integrate FFmpeg as a library (libavcodec, libavformat, libavutil)
- Can use hardware encoders (NVENC, QSV, AMF) with `AV_PIX_FMT_D3D11`
- The [Medium article by Ori Gold](https://medium.com/swlh/streaming-video-with-ffmpeg-and-directx-11-7395fcb372c4) documents this approach in detail

**Option C: NVENC direct encoding (zero-copy, NVIDIA only)**
```
GPU render -> ID3D11Texture2D -> NVENC register resource -> encode -> RTMP
```
- NVIDIA Video Codec SDK can encode directly from D3D11 textures
- No CPU readback at all
- Requires NVIDIA GPU

**Option D: Media Foundation + FFmpeg transmux**
```
GPU render -> staging -> Media Foundation H.264 encoder -> named pipe -> FFmpeg avio_read -> RTMP
```
- Windows-native H.264 encoding via MFT (hardware accelerated)
- FFmpeg only handles transmuxing to FLV/RTMP (no transcoding)
- Documented in [Scali's blog](https://scalibq.wordpress.com/2023/09/26/implementing-live-video-streaming-in-software/)

### Recommended: Option A for simplicity, Option C for performance

---

## 4. Existing Native Streaming/Rendering Frameworks

### libobs (OBS Studio's Core Library)

**The most battle-tested option for native streaming.**

Architecture:
- `obs_startup()` -> `obs_reset_video()` -> `obs_reset_audio()` -> `obs_load_all_modules()`
- Custom graphics abstraction wrapping D3D11/OpenGL
- Scene/source/filter/output/encoder plugin system
- Dedicated video thread, audio thread, encoder threads
- Built-in RTMP output, hardware encoder support

**Can be used without OBS GUI**:
- [obs-headless](https://github.com/a-rose/obs-headless): Headless OBS in Docker, controls via gRPC
- [obs-studio-node](https://github.com/streamlabs/obs-studio-node): Node.js/Electron bindings for libobs (used by Streamlabs)
- Create custom sources that render VRM content
- Create custom filters for overlays

**Limitations**:
- Complex API surface
- Requires loading OBS plugin modules
- Shader effects system uses custom HLSL-like format
- Must run from OBS install directory to find shader files
- GPL-2.0 license (viral)

### VSeeFace Architecture

VSeeFace is a Windows VRM avatar puppeteering app:
- **Built with Unity** (not a custom engine)
- Uses UniVRM for VRM loading
- DirectX rendering (via Unity's graphics pipeline)
- Custom MToon-like shaders
- Outputs via game capture / Spout2 / virtual camera
- Supports VRM 0.x only (not 1.0)

### Approach Comparison

| Approach | Complexity | Performance | VRM Support | License |
|----------|-----------|------------|-------------|---------|
| libobs + custom source | High | Excellent | Must implement | GPL-2.0 |
| Custom D3D11 + Filament/bgfx | High | Excellent | Must implement | MIT/BSD |
| Godot + godot-vrm | Medium | Good | Built-in | MIT |
| Unity + UniVRM (headless build) | Medium | Good | Built-in | Unity license |
| Custom .NET (Veldrid/Silk.NET + SharpGLTF) | High | Good | Must implement | MIT |

---

## 5. Audio Without Browser

### NAudio (.NET)

The most complete .NET audio library:
- `MixingSampleProvider`: Mix multiple audio streams (TTS + BGM)
- `WaveOutEvent`: Low-latency playback via waveOut API
- `WasapiOut`: WASAPI playback for lowest latency
- `AudioFileReader`: Load WAV, MP3, AIFF
- Volume control per-stream
- Fire-and-forget playback pattern
- MIT license

### XAudio2 (Windows Native C++)

Microsoft's game audio API:
- Source voices, submix voices, mastering voices
- Hardware-mixed audio with very low latency (~10ms)
- Built-in filters (low/high/band pass)
- Submix architecture perfect for TTS + BGM mixing
- Built into Windows (no external dependencies)

### WASAPI (Windows Audio Session API)

Lowest-level Windows audio API:
- Exclusive mode for minimum latency
- **Loopback capture**: Capture what's playing on the audio device
  - Can feed loopback audio to FFmpeg for stream audio
  - [audiotee-wasapi](https://github.com/huxinhai/audiotee-wasapi): WASAPI loopback to FFmpeg example

### Audio for Streaming Pipeline

Two approaches:
1. **Application-mixed**: Mix TTS+BGM in app (NAudio/XAudio2), pipe PCM to FFmpeg alongside video
2. **Loopback capture**: Play audio normally via speakers, capture via WASAPI loopback, feed to FFmpeg

Approach 1 is cleaner and more reliable.

---

## 6. Recommended Architecture

### Option A: Custom C++ Application (Maximum Control)

```
+------------------+     +------------------+     +---------+
| D3D11 Renderer   |     | Staging Texture  |     | FFmpeg  |
|                  |     |                  |     | Process |
| Filament/bgfx    |---->| Double-buffered  |---->| stdin   |---> RTMP
| + tinygltf       |     | GPU readback     |     | pipe    |
| + VRM.h          |     +------------------+     +---------+
| + MToon shader   |
| + Direct2D       |     +------------------+
|   overlays       |     | XAudio2          |---> PCM to FFmpeg
+------------------+     | TTS + BGM mixer  |     audio pipe
                          +------------------+
```

**Pros**: Maximum performance, no runtime dependencies, full control
**Cons**: Must implement MToon shader, SpringBone physics, BlendShape system from scratch
**Effort**: ~3-6 months for one developer

### Option B: .NET Application (Pragmatic Balance)

```
+--------------------+     +---------+
| Veldrid/.NET       |     | FFmpeg  |
| + SharpGLTF        |---->| Process |---> RTMP
| + Custom MToon     |     +---------+
| + SkiaSharp/D2D    |
| + NAudio mixer     |----> audio pipe
+--------------------+
```

**Pros**: C# productivity, good libraries, cross-platform potential
**Cons**: Must still implement MToon, SpringBone; .NET GC pauses possible
**Effort**: ~2-4 months

### Option C: Godot Engine (Fastest Path, Blocked by Offscreen)

```
+------------------+     +---------+
| Godot 4.x        |     | FFmpeg  |
| + godot-vrm       |---->| Process |---> RTMP
| + SubViewport    |     +---------+
| + 2D overlays    |
+------------------+
```

**Pros**: VRM support already built, MToon shader done, scene editor
**Cons**: **No offscreen rendering support yet** (proposal stage). Would need a visible window or virtual display. Licensing is fine (MIT).
**Effort**: ~2-4 weeks if offscreen rendering existed

### Option D: libobs + Custom VRM Source Plugin (Hybrid)

```
+-------------------+     +---------+
| libobs            |     | RTMP    |
| + Custom source:  |---->| Output  |---> Twitch
|   - D3D11 VRM     |     +---------+
|   - Filament      |
|   - Direct2D      |
| + Audio encoder   |
+-------------------+
```

**Pros**: Proven streaming pipeline, encoder support, reconnection logic, audio mixing
**Cons**: GPL-2.0 license, complex integration, must write OBS plugin in C
**Effort**: ~2-3 months

### Option E: Unity Headless Build (Path of Least Resistance for VRM)

```
+-------------------+     +---------+
| Unity Build       |     | FFmpeg  |
| + UniVRM          |---->| Process |---> RTMP
| + Render Texture  |     +---------+
| + UGUI overlays   |
| + Audio Mixer     |----> audio pipe
+-------------------+
```

**Pros**: Complete VRM support (UniVRM), MToon shader, SpringBone, BlendShape all working out of the box. Render-to-texture is straightforward. Audio mixer built in.
**Cons**: Unity license required for commercial use. Not truly "headless" -- needs GPU. Large binary size. Less control than custom solution.
**Effort**: ~2-4 weeks

---

## 7. Key Findings Summary

1. **No single library provides "load VRM and render natively on Windows"**. You must combine a glTF loader + VRM extension parser + 3D renderer + MToon shader implementation.

2. **MToon shader reimplementation** is the biggest technical challenge. The spec is documented, and reference GLSL implementations exist in three-vrm, but porting to HLSL for D3D11 requires shader programming expertise.

3. **SpringBone physics** is well-documented (Verlet integration) with reference implementations in TypeScript (babylon-vrm-loader) and C++ (VRM4U for Unreal).

4. **Direct2D + DirectWrite** is the natural choice for 2D overlays on Windows, with first-class D3D11 interop via DXGI surfaces.

5. **GPU readback** for streaming is a solved problem: double-buffered staging textures + pipe to FFmpeg.

6. **libobs** is the most production-ready streaming framework but has GPL license and high complexity.

7. **Godot + godot-vrm** would be ideal but is blocked by lack of offscreen rendering support.

8. **Unity + UniVRM** is the path of least resistance if Unity licensing is acceptable -- everything works out of the box.

9. For a truly native solution, **Filament (C++) or Veldrid (.NET)** as the rendering engine + **tinygltf/SharpGLTF** for loading + custom MToon/SpringBone implementation is the recommended approach.

---

## Sources

### VRM Format & Libraries
- [VRM.h - C++ header-only VRM library](https://github.com/infosia/VRM.h)
- [UniVRM - Unity VRM implementation](https://github.com/vrm-c/UniVRM)
- [VRM Specification](https://github.com/vrm-c/vrm-specification)
- [three-vrm - Three.js VRM](https://github.com/pixiv/three-vrm)
- [godot-vrm - Godot VRM addon](https://github.com/V-Sekai/godot-vrm)
- [VRM4U - Unreal Engine VRM](https://github.com/ruyo/VRM4U)
- [VRMC_materials_mtoon specification](https://github.com/vrm-c/vrm-specification/blob/master/specification/VRMC_materials_mtoon-1.0/README.md)
- [MToon overview (Cluster)](https://medium.com/@cluster_official/an-overview-of-the-mtoon-shader-settings-05d98a4a1299)
- [VRM format info (LOC)](https://www.loc.gov/preservation/digital/formats/fdd/fdd000564.shtml)

### glTF Loaders
- [tinygltf - C++ glTF 2.0](https://github.com/syoyo/tinygltf)
- [Assimp - C++ model importer](https://github.com/assimp/assimp)
- [SharpGLTF - .NET glTF](https://github.com/vpenades/SharpGLTF)

### 3D Rendering Engines
- [Filament - Google PBR engine](https://github.com/google/filament)
- [bgfx - Cross-platform rendering](https://github.com/bkaradzic/bgfx)
- [Diligent Engine](https://github.com/DiligentGraphics/DiligentEngine)
- [Magnum - C++ graphics](https://github.com/mosra/magnum)
- [Silk.NET - .NET graphics](https://github.com/dotnet/Silk.NET)
- [Veldrid - .NET GPU library](https://github.com/veldrid/veldrid)

### DirectX & 2D Rendering
- [Direct2D + Direct3D interop (Microsoft)](https://learn.microsoft.com/en-us/windows/win32/direct2d/direct2d-and-direct3d-interoperation-overview)
- [DirectWrite text rendering](https://learn.microsoft.com/en-us/windows/win32/direct2d/direct2d-and-directwrite)
- [D3D11 staging texture readback (gist)](https://gist.github.com/iondune/1c8197083408f377d9f2494d3dcd6523)
- [SkiaSharp](https://github.com/mono/SkiaSharp)

### Streaming Pipeline
- [Streaming Video with FFmpeg + DirectX 11 (Medium)](https://medium.com/swlh/streaming-video-with-ffmpeg-and-directx-11-7395fcb372c4)
- [Live video streaming implementation (Scali's blog)](https://scalibq.wordpress.com/2023/09/26/implementing-live-video-streaming-in-software/)
- [NVENC direct D3D11 texture encoding (NVIDIA)](https://forums.developer.nvidia.com/t/nvenc-realtime-encoding-using-id3d11texture2d-as-input/29144)
- [NVIDIA Video Codec SDK](https://developer.nvidia.com/video-codec-sdk)
- [Media Foundation H.264 Encoder (Microsoft)](https://learn.microsoft.com/en-us/windows/win32/medfound/h-264-video-encoder)
- [FFmpeg with NVIDIA GPU (docs)](https://docs.nvidia.com/video-technologies/video-codec-sdk/13.0/ffmpeg-with-nvidia-gpu/index.html)

### OBS / libobs
- [OBS Backend Design](https://docs.obsproject.com/backend-design)
- [libobs Core (DeepWiki)](https://deepwiki.com/obsproject/obs-studio/2.1-libobs-core)
- [obs-headless - Headless OBS in Docker](https://github.com/a-rose/obs-headless)
- [obs-studio-node - Node.js bindings](https://github.com/streamlabs/obs-studio-node)
- [OBS rendering graphics docs](https://docs.obsproject.com/graphics)

### Audio
- [NAudio - .NET audio library](https://github.com/naudio/NAudio)
- [NAudio mixing guide](https://www.markheath.net/post/mixing-and-looping-with-naudio)
- [XAudio2 Introduction (Microsoft)](https://learn.microsoft.com/en-us/windows/win32/xaudio2/xaudio2-introduction)
- [WASAPI loopback recording (Microsoft)](https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording)
- [audiotee-wasapi - WASAPI capture tool](https://github.com/huxinhai/audiotee-wasapi)

### Game Engines
- [Godot offscreen rendering proposal](https://github.com/godotengine/godot-proposals/issues/5790)
- [Godot headless mode proposal](https://github.com/godotengine/godot-proposals/issues/991)
- [Stride Engine](https://github.com/stride3d/stride)
- [VSeeFace](https://www.vseeface.icu/)

### Misc
- [babylon-vrm-loader (SpringBone TypeScript reference)](https://github.com/virtual-cast/babylon-vrm-loader)
- [Flyleaf - .NET FFmpeg/DirectX player](https://github.com/SuRGeoNix/Flyleaf)
- [wgpu - Rust WebGPU native](https://github.com/gfx-rs/wgpu)
