/**
 * Zero-Dependency Vanilla WebGL2 Instanced 3D Trajectory Viewer for LAMMPS.
 *
 * Upgraded Features:
 * - Instanced spheres with Blinn-Phong lighting, subtle Fresnel rim-lighting, and data-tied glow.
 * - Per-atom physical field coloring: Viridis colormap for Kinetic Energy and Von Mises Stress.
 * - Per-frame and Whole-run normalization with physical units legend.
 * - Physically-honest smooth motion via client-side sub-frame interpolation with PBC unwrapping.
 * - Persistent always-visible "Simulated" vs "Interpolated" timestep indicator.
 * - Step-function scalar field holding (never fabricates intermediate stress/temperature physics).
 */

const UNIT_PHYSICAL_LABELS = {
  lj: {
    name: "Lennard-Jones (Reduced)",
    ke: "ε",
    stress: "ε/σ³"
  },
  real: {
    name: "Real",
    ke: "kcal/mol",
    stress: "atm"
  },
  metal: {
    name: "Metal",
    ke: "eV",
    stress: "bar"
  },
  electron: {
    name: "Electron",
    ke: "Hartree",
    stress: "Bohr-stress"
  },
  si: {
    name: "SI",
    ke: "J",
    stress: "Pa"
  },
  cgs: {
    name: "CGS",
    ke: "erg",
    stress: "dyn/cm²"
  }
};

class TrajectoryViewer {
  constructor(canvas, options = {}) {
    this.canvas = canvas;
    this.gl = canvas.getContext('webgl2', { antialias: true, alpha: false });
    if (!this.gl) {
      console.warn("WebGL2 not supported in this browser.");
      return;
    }

    this.options = Object.assign({
      onFrameChange: null,
      onTimestepChange: null,
      onColorbarChange: null,
      defaultRadius: 0.8,
      defaultColor: [0.6, 0.4, 0.9]
    }, options);

    this.frames = [];
    this.currentFrameIdx = 0;
    this.fractionalFrame = 0.0;
    this.isPlaying = false;
    this.isLiveFollowing = true;
    this.playbackSpeed = 8.0; // real frames per second target
    this.lastRenderTime = 0;

    // Field Coloring & Normalization State
    this.colorMode = "element"; // "element" | "kinetic_energy" | "von_mises_stress"
    this.normMode = "frame";    // "frame" | "run"
    this.units = "lj";
    this.availableFields = ["element"];
    this.isSynthetic = false;

    // Trajectory-wide statistical extrema for "run" normalization
    this.runStats = {
      kinetic_energy: { min: Infinity, max: -Infinity },
      von_mises_stress: { min: Infinity, max: -Infinity }
    };

    this.metadata = { types: {}, box_size: [16.2, 16.2, 16.2] };

    // Camera state (orbit controls)
    this.camera = {
      target: [8.1, 8.1, 8.1],
      distance: 35.0,
      yaw: 0.6,
      pitch: 0.4,
      isDragging: false,
      isPanning: false,
      lastX: 0,
      lastY: 0
    };

    this._initShaders();
    this._initSphereGeometry();
    this._initBoxGeometry();
    this._initEventListeners();
    this._resize();

    // Start 60fps render loop
    this._renderLoop = this._renderLoop.bind(this);
    requestAnimationFrame(this._renderLoop);
  }

  _initShaders() {
    const gl = this.gl;

    // Atom Shaders (Instanced Spheres with Blinn-Phong + Fresnel + Viridis Colormap)
    const vsSource = `#version 300 es
      layout(location = 0) in vec3 a_vertex;
      layout(location = 1) in vec3 a_normal;
      layout(location = 2) in vec3 a_instancePos;
      layout(location = 3) in vec3 a_instanceColor;
      layout(location = 4) in float a_instanceRadius;
      layout(location = 5) in float a_instanceScalar;

      uniform mat4 u_proj;
      uniform mat4 u_view;

      out vec3 v_normal;
      out vec3 v_color;
      out vec3 v_pos;
      out float v_scalar;

      void main() {
        vec3 worldPos = a_instancePos + a_vertex * a_instanceRadius;
        v_normal = a_normal;
        v_color = a_instanceColor;
        v_pos = (u_view * vec4(worldPos, 1.0)).xyz;
        v_scalar = a_instanceScalar;
        gl_Position = u_proj * vec4(v_pos, 1.0);
      }
    `;

    const fsSource = `#version 300 es
      precision highp float;

      in vec3 v_normal;
      in vec3 v_color;
      in vec3 v_pos;
      in float v_scalar;

      uniform int u_colorMode;      // 0 = element (CPK), 1 = scalar (Viridis)
      uniform int u_isInterpolated; // 1 = visual sub-frame, 0 = simulated frame

      out vec4 fragColor;

      // Accurate Viridis colormap polynomial approximation (< 0.5% max error across [0, 1])
      vec3 viridis(float t) {
        t = clamp(t, 0.0, 1.0);
        const vec4 c0 = vec4(0.277727327223414, 0.005407344544948, 0.334099805335305, 0.0);
        const vec4 c1 = vec4(0.105050559914945, 1.404613529898575, 1.384590162594785, 0.0);
        const vec4 c2 = vec4(-0.330861828725554, 0.214878269837321, 0.095095163028236, 0.0);
        const vec4 c3 = vec4(-4.634230498983486, -5.729194970669886, -19.34199735841856, 0.0);
        const vec4 c4 = vec4(6.228269936347081, 14.17993336680509, 56.69055260068105, 0.0);
        const vec4 c5 = vec4(4.776384997670288, -13.74958608373133, -65.35303263337234, 0.0);
        const vec4 c6 = vec4(-5.435455860734699, 4.645852612178535, 26.3124352495832, 0.0);
        return clamp(c0.rgb + t*(c1.rgb + t*(c2.rgb + t*(c3.rgb + t*(c4.rgb + t*(c5.rgb + t*c6.rgb))))), 0.0, 1.0);
      }

      void main() {
        vec3 n = normalize(v_normal);
        // Directional key light + soft ambient
        vec3 lightDir = normalize(vec3(0.55, 1.1, 0.75));
        float diff = max(dot(n, lightDir), 0.0);
        float ambient = 0.28;

        // View direction in view-space
        vec3 viewDir = normalize(-v_pos);
        vec3 halfDir = normalize(lightDir + viewDir);
        float spec = pow(max(dot(n, halfDir), 0.0), 32.0) * 0.42;

        // Base atom color: Element (CPK) vs Viridis field colormap
        vec3 baseColor = (u_colorMode == 0) ? v_color : viridis(v_scalar);

        // Subtle Fresnel / rim-light for depth and volume
        float fresnel = pow(1.0 - max(dot(n, viewDir), 0.0), 2.5);
        vec3 rim = vec3(0.35) * fresnel;

        // Data-motivated glow on high-value atoms when in physical data mode
        vec3 dataGlow = vec3(0.0);
        if (u_colorMode != 0) {
          float highIntensity = smoothstep(0.70, 1.0, v_scalar);
          dataGlow = baseColor * highIntensity * fresnel * 0.8;
        }

        // Shaded atom color
        vec3 color = baseColor * (ambient + diff * 0.72) + vec3(spec) + rim * 0.4 + dataGlow;

        // In visual sub-frame interpolation, subtly soften saturation so physical state distinction is respected
        if (u_isInterpolated == 1) {
          float lum = dot(color, vec3(0.299, 0.587, 0.114));
          color = mix(color, vec3(lum), 0.12);
        }

        fragColor = vec4(color, 1.0);
      }
    `;

    this.atomProgram = this._createProgram(vsSource, fsSource);

    // Box Shaders (Wireframe Cube with Depth-Appropriate Fading)
    const boxVs = `#version 300 es
      layout(location = 0) in vec3 a_vertex;
      uniform mat4 u_proj;
      uniform mat4 u_view;
      out float v_depth;

      void main() {
        vec4 viewPos = u_view * vec4(a_vertex, 1.0);
        v_depth = -viewPos.z;
        gl_Position = u_proj * viewPos;
      }
    `;
    const boxFs = `#version 300 es
      precision highp float;
      in float v_depth;
      out vec4 fragColor;

      void main() {
        // Depth-appropriate fading: softer in the background, sharper near the camera
        float alpha = clamp(0.55 - v_depth * 0.003, 0.15, 0.65);
        fragColor = vec4(0.38, 0.52, 0.85, alpha);
      }
    `;
    this.boxProgram = this._createProgram(boxVs, boxFs);
  }

  _createShader(type, src) {
    const gl = this.gl;
    const shader = gl.createShader(type);
    gl.shaderSource(shader, src);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      console.error(gl.getShaderInfoLog(shader));
      gl.deleteShader(shader);
      return null;
    }
    return shader;
  }

  _createProgram(vsSrc, fsSrc) {
    const gl = this.gl;
    const vs = this._createShader(gl.VERTEX_SHADER, vsSrc);
    const fs = this._createShader(gl.FRAGMENT_SHADER, fsSrc);
    const prog = gl.createProgram();
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      console.error(gl.getProgramInfoLog(prog));
      return null;
    }
    return prog;
  }

  _initSphereGeometry() {
    const gl = this.gl;
    // UV Sphere (~160 triangles)
    const latBands = 10;
    const lonBands = 12;
    const positions = [];
    const normals = [];

    for (let lat = 0; lat < latBands; lat++) {
      const theta1 = (lat * Math.PI) / latBands;
      const theta2 = ((lat + 1) * Math.PI) / latBands;
      for (let lon = 0; lon < lonBands; lon++) {
        const phi1 = (lon * 2 * Math.PI) / lonBands;
        const phi2 = ((lon + 1) * 2 * Math.PI) / lonBands;

        const p1 = [Math.sin(theta1) * Math.cos(phi1), Math.cos(theta1), Math.sin(theta1) * Math.sin(phi1)];
        const p2 = [Math.sin(theta1) * Math.cos(phi2), Math.cos(theta1), Math.sin(theta1) * Math.sin(phi2)];
        const p3 = [Math.sin(theta2) * Math.cos(phi2), Math.cos(theta2), Math.sin(theta2) * Math.sin(phi2)];
        const p4 = [Math.sin(theta2) * Math.cos(phi1), Math.cos(theta2), Math.sin(theta2) * Math.sin(phi1)];

        // Quad -> 2 Triangles: p1-p2-p3, p1-p3-p4
        positions.push(...p1, ...p2, ...p3, ...p1, ...p3, ...p4);
        normals.push(...p1, ...p2, ...p3, ...p1, ...p3, ...p4);
      }
    }

    this.sphereVertexCount = positions.length / 3;

    // Atom VAO
    this.atomVAO = gl.createVertexArray();
    gl.bindVertexArray(this.atomVAO);

    // Attribute 0: Sphere Vertices
    const posVBO = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, posVBO);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(positions), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);

    // Attribute 1: Sphere Normals
    const normVBO = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, normVBO);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(normals), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 0, 0);

    // Instanced Buffers: Position (vec3), Color (vec3), Radius (float), Scalar (float)
    this.instancePosBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.instancePosBuffer);
    gl.enableVertexAttribArray(2);
    gl.vertexAttribPointer(2, 3, gl.FLOAT, false, 0, 0);
    gl.vertexAttribDivisor(2, 1);

    this.instanceColorBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.instanceColorBuffer);
    gl.enableVertexAttribArray(3);
    gl.vertexAttribPointer(3, 3, gl.FLOAT, false, 0, 0);
    gl.vertexAttribDivisor(3, 1);

    this.instanceRadiusBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.instanceRadiusBuffer);
    gl.enableVertexAttribArray(4);
    gl.vertexAttribPointer(4, 1, gl.FLOAT, false, 0, 0);
    gl.vertexAttribDivisor(4, 1);

    this.instanceScalarBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.instanceScalarBuffer);
    gl.enableVertexAttribArray(5);
    gl.vertexAttribPointer(5, 1, gl.FLOAT, false, 0, 0);
    gl.vertexAttribDivisor(5, 1);

    gl.bindVertexArray(null);
    this.instanceCount = 0;
  }

  _initBoxGeometry() {
    const gl = this.gl;
    this.boxVAO = gl.createVertexArray();
    gl.bindVertexArray(this.boxVAO);

    this.boxVBO = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.boxVBO);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);

    gl.bindVertexArray(null);
    this._updateBoxGeometry([0, 16.2], [0, 16.2], [0, 16.2]);
  }

  _updateBoxGeometry(bx, by, bz) {
    const x0 = bx[0], x1 = bx[1];
    const y0 = by[0], y1 = by[1];
    const z0 = bz[0], z1 = bz[1];

    // 12 lines = 24 vertices
    const lines = [
      x0, y0, z0,  x1, y0, z0,
      x1, y0, z0,  x1, y1, z0,
      x1, y1, z0,  x0, y1, z0,
      x0, y1, z0,  x0, y0, z0,

      x0, y0, z1,  x1, y0, z1,
      x1, y0, z1,  x1, y1, z1,
      x1, y1, z1,  x0, y1, z1,
      x0, y1, z1,  x0, y0, z1,

      x0, y0, z0,  x0, y0, z1,
      x1, y0, z0,  x1, y0, z1,
      x1, y1, z0,  x1, y1, z1,
      x0, y1, z0,  x0, y1, z1,
    ];

    const gl = this.gl;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.boxVBO);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(lines), gl.STATIC_DRAW);
  }

  _initEventListeners() {
    const canvas = this.canvas;

    canvas.addEventListener('mousedown', (e) => {
      this.camera.isDragging = (e.button === 0);
      this.camera.isPanning = (e.button === 2 || (e.button === 0 && e.shiftKey));
      this.camera.lastX = e.clientX;
      this.camera.lastY = e.clientY;
    });

    window.addEventListener('mousemove', (e) => {
      if (!this.camera.isDragging && !this.camera.isPanning) return;
      const dx = e.clientX - this.camera.lastX;
      const dy = e.clientY - this.camera.lastY;
      this.camera.lastX = e.clientX;
      this.camera.lastY = e.clientY;

      if (this.camera.isPanning) {
        const factor = this.camera.distance * 0.002;
        this.camera.target[0] -= dx * factor;
        this.camera.target[1] += dy * factor;
      } else if (this.camera.isDragging) {
        this.camera.yaw += dx * 0.01;
        this.camera.pitch = Math.max(-1.5, Math.min(1.5, this.camera.pitch + dy * 0.01));
      }
    });

    window.addEventListener('mouseup', () => {
      this.camera.isDragging = false;
      this.camera.isPanning = false;
    });

    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      this.camera.distance = Math.max(5.0, Math.min(150.0, this.camera.distance + e.deltaY * 0.05));
    }, { passive: false });

    canvas.addEventListener('contextmenu', (e) => e.preventDefault());
    window.addEventListener('resize', () => this._resize());
  }

  _resize() {
    const rect = this.canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const width = Math.floor((rect.width || 800) * dpr);
    const height = Math.floor((rect.height || 400) * dpr);

    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
      this.gl.viewport(0, 0, width, height);
    }
  }

  setMetadata(meta) {
    if (!meta) return;
    this.metadata = meta;
    if (meta.units) this.units = meta.units.toLowerCase();
    if (meta.available_fields) this.availableFields = meta.available_fields;
    if (meta.is_synthetic !== undefined) this.isSynthetic = !!meta.is_synthetic;

    if (meta.box_size && meta.box_size.length === 3) {
      const bs = meta.box_size;
      this.camera.target = [bs[0] / 2, bs[1] / 2, bs[2] / 2];
      this.camera.distance = Math.max(bs[0], bs[1], bs[2]) * 2.2;
      this._updateBoxGeometry([0, bs[0]], [0, bs[1]], [0, bs[2]]);
    }
    this._emitColorbarUpdate();
  }

  setColorMode(mode) {
    if (["element", "kinetic_energy", "von_mises_stress"].includes(mode)) {
      this.colorMode = mode;
      this.seek(this.fractionalFrame);
      this._emitColorbarUpdate();
    }
  }

  setNormMode(norm) {
    if (["frame", "run"].includes(norm)) {
      this.normMode = norm;
      this.seek(this.fractionalFrame);
      this._emitColorbarUpdate();
    }
  }

  _parseHexColor(hex) {
    if (!hex) return [0.4, 0.7, 1.0];
    hex = hex.replace('#', '');
    if (hex.length === 3) hex = hex.split('').map(c => c + c).join('');
    const num = parseInt(hex, 16);
    return [(num >> 16 & 255) / 255, (num >> 8 & 255) / 255, (num & 255) / 255];
  }

  addFrame(frame) {
    if (!frame) return;
    this.frames.push(frame);

    // Update whole-run statistics for KE and Stress
    const atoms = frame.atoms || [];
    for (let i = 0; i < atoms.length; i++) {
      const at = atoms[i];
      let ke = null, stress = null;
      if (Array.isArray(at)) {
        ke = at[5];
        stress = at[6];
      } else {
        ke = at.ke !== undefined ? at.ke : at.c_atomKE;
        stress = at.von_mises_stress !== undefined ? at.von_mises_stress : at.v_vonMises;
      }
      if (ke !== null && ke !== undefined && !isNaN(ke)) {
        this.runStats.kinetic_energy.min = Math.min(this.runStats.kinetic_energy.min, Number(ke));
        this.runStats.kinetic_energy.max = Math.max(this.runStats.kinetic_energy.max, Number(ke));
      }
      if (stress !== null && stress !== undefined && !isNaN(stress)) {
        this.runStats.von_mises_stress.min = Math.min(this.runStats.von_mises_stress.min, Number(stress));
        this.runStats.von_mises_stress.max = Math.max(this.runStats.von_mises_stress.max, Number(stress));
      }
    }

    if (frame.box && frame.box.length === 3) {
      this._updateBoxGeometry(frame.box[0], frame.box[1], frame.box[2]);
    }

    // If live streaming or first frame, auto-seek to latest frame
    if (this.isLiveFollowing || this.frames.length === 1) {
      this.seek(this.frames.length - 1);
    }

    if (this.options.onFrameChange) {
      this.options.onFrameChange(this.currentFrameIdx, this.frames.length);
    }
  }

  /**
   * Seeks to a real or sub-frame interpolated index.
   *
   * @param {number} fractionalIdx - Float index e.g. 2.45
   */
  seek(fractionalIdx) {
    if (this.frames.length === 0) return;

    fractionalIdx = Math.max(0, Math.min(this.frames.length - 1, fractionalIdx));
    this.fractionalFrame = fractionalIdx;

    const idxA = Math.floor(fractionalIdx);
    const idxB = Math.min(this.frames.length - 1, idxA + 1);
    const alpha = fractionalIdx - idxA;

    this.currentFrameIdx = idxA;
    const isInterpolated = (alpha > 0.001 && idxA !== idxB);

    const frameA = this.frames[idxA];
    const frameB = this.frames[idxB];
    const atomsA = frameA.atoms || [];
    const atomsB = frameB.atoms || [];
    const count = atomsA.length;
    this.instanceCount = count;

    if (count === 0) return;

    // Simulation box dimensions for PBC unwrapping
    let lx = 16.2, ly = 16.2, lz = 16.2;
    if (frameA.box && frameA.box.length === 3) {
      lx = Math.max(0.1, frameA.box[0][1] - frameA.box[0][0]);
      ly = Math.max(0.1, frameA.box[1][1] - frameA.box[1][0]);
      lz = Math.max(0.1, frameA.box[2][1] - frameA.box[2][0]);
    }

    // Determine scalar field min / max for normalization
    let minScalar = 0.0;
    let maxScalar = 1.0;

    if (this.colorMode !== "element") {
      const fieldKey = this.colorMode; // "kinetic_energy" or "von_mises_stress"
      if (this.normMode === "run") {
        minScalar = this.runStats[fieldKey].min;
        maxScalar = this.runStats[fieldKey].max;
      } else {
        // Current frame min / max
        let fMin = Infinity, fMax = -Infinity;
        for (let i = 0; i < count; i++) {
          const at = atomsA[i];
          const val = Array.isArray(at)
            ? (fieldKey === "kinetic_energy" ? at[5] : at[6])
            : (fieldKey === "kinetic_energy" ? (at.ke ?? at.c_atomKE) : (at.von_mises_stress ?? at.v_vonMises));
          if (val !== null && val !== undefined && !isNaN(val)) {
            fMin = Math.min(fMin, Number(val));
            fMax = Math.max(fMax, Number(val));
          }
        }
        minScalar = fMin;
        maxScalar = fMax;
      }
      if (!isFinite(minScalar) || !isFinite(maxScalar) || minScalar === maxScalar) {
        minScalar = 0.0;
        maxScalar = 1.0;
      }
    }

    const posArray = new Float32Array(count * 3);
    const colorArray = new Float32Array(count * 3);
    const radiusArray = new Float32Array(count);
    const scalarArray = new Float32Array(count);

    const typeMeta = this.metadata.types || {};

    for (let i = 0; i < count; i++) {
      const atA = atomsA[i];
      let idA, tA, xA, yA, zA, keA, stressA;
      if (Array.isArray(atA)) {
        idA = atA[0]; tA = atA[1]; xA = atA[2]; yA = atA[3]; zA = atA[4]; keA = atA[5]; stressA = atA[6];
      } else {
        idA = atA.id || (i + 1); tA = atA.type || 1; xA = atA.x; yA = atA.y; zA = atA.z;
        keA = atA.ke ?? atA.c_atomKE; stressA = atA.von_mises_stress ?? atA.v_vonMises;
      }

      // Position interpolation with PBC unwrapping (Minimum Image Convention)
      let x = xA, y = yA, z = zA;
      if (isInterpolated && i < atomsB.length) {
        const atB = atomsB[i];
        let xB = Array.isArray(atB) ? atB[2] : atB.x;
        let yB = Array.isArray(atB) ? atB[3] : atB.y;
        let zB = Array.isArray(atB) ? atB[4] : atB.z;

        let dx = xB - xA;
        if (dx > lx * 0.5) dx -= lx;
        else if (dx < -lx * 0.5) dx += lx;

        let dy = yB - yA;
        if (dy > ly * 0.5) dy -= ly;
        else if (dy < -ly * 0.5) dy += ly;

        let dz = zB - zA;
        if (dz > lz * 0.5) dz -= lz;
        else if (dz < -lz * 0.5) dz += lz;

        x = (xA + alpha * dx + lx) % lx;
        y = (yA + alpha * dy + ly) % ly;
        z = (zA + alpha * dz + lz) % lz;
      }

      posArray[i * 3 + 0] = x;
      posArray[i * 3 + 1] = y;
      posArray[i * 3 + 2] = z;

      // Base CPK Element color
      const tInfo = typeMeta[String(tA)] || {};
      const rgb = tInfo.color ? this._parseHexColor(tInfo.color) : (tA === 2 ? [0.95, 0.95, 0.95] : [0.2, 0.7, 0.9]);
      colorArray[i * 3 + 0] = rgb[0];
      colorArray[i * 3 + 1] = rgb[1];
      colorArray[i * 3 + 2] = rgb[2];

      radiusArray[i] = tInfo.radius ? (tInfo.radius * 0.45) : (tA === 2 ? 0.45 : 0.75);

      // STEP FUNCTION: Field scalar strictly held from frame A without fabricating intermediate stress
      let rawScalar = (this.colorMode === "kinetic_energy") ? keA : stressA;
      if (rawScalar !== null && rawScalar !== undefined && !isNaN(rawScalar)) {
        scalarArray[i] = Math.max(0.0, Math.min(1.0, (Number(rawScalar) - minScalar) / Math.max(1e-12, maxScalar - minScalar)));
      } else {
        scalarArray[i] = 0.0;
      }
    }

    const gl = this.gl;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.instancePosBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, posArray, gl.DYNAMIC_DRAW);

    gl.bindBuffer(gl.ARRAY_BUFFER, this.instanceColorBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, colorArray, gl.DYNAMIC_DRAW);

    gl.bindBuffer(gl.ARRAY_BUFFER, this.instanceRadiusBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, radiusArray, gl.DYNAMIC_DRAW);

    gl.bindBuffer(gl.ARRAY_BUFFER, this.instanceScalarBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, scalarArray, gl.DYNAMIC_DRAW);

    this.isCurrentInterpolated = isInterpolated;

    // Trigger UI status callbacks
    if (this.options.onFrameChange) {
      this.options.onFrameChange(idxA, this.frames.length);
    }

    if (this.options.onTimestepChange) {
      const ts = frameA.timestep !== undefined ? frameA.timestep : idxA;
      this.options.onTimestepChange(ts, isInterpolated, idxA, this.frames.length);
    }

    this._emitColorbarUpdate(minScalar, maxScalar);
  }

  _emitColorbarUpdate(minVal, maxVal) {
    if (!this.options.onColorbarChange) return;

    const uInfo = UNIT_PHYSICAL_LABELS[this.units] || UNIT_PHYSICAL_LABELS.lj;
    const unitSymbol = (this.colorMode === "kinetic_energy") ? uInfo.ke : uInfo.stress;

    this.options.onColorbarChange({
      colorMode: this.colorMode,
      normMode: this.normMode,
      units: this.units,
      unitSymbol: unitSymbol,
      min: minVal !== undefined ? minVal : 0.0,
      mid: (minVal !== undefined && maxVal !== undefined) ? (minVal + maxVal) * 0.5 : 0.5,
      max: maxVal !== undefined ? maxVal : 1.0,
      isSynthetic: this.isSynthetic,
      availableFields: this.availableFields
    });
  }

  play() {
    this.isPlaying = true;
    this.lastRenderTime = performance.now();
  }

  pause() {
    this.isPlaying = false;
  }

  togglePlay() {
    if (this.isPlaying) this.pause();
    else this.play();
  }

  setPlaybackSpeed(mult) {
    this.playbackSpeed = 8.0 * (mult || 1.0);
  }

  resetCamera() {
    if (this.metadata && this.metadata.box_size && this.metadata.box_size.length === 3) {
      const bs = this.metadata.box_size;
      this.camera.target = [bs[0] / 2, bs[1] / 2, bs[2] / 2];
      this.camera.distance = Math.max(bs[0], bs[1], bs[2]) * 2.2;
    } else {
      this.camera.target = [8.1, 8.1, 8.1];
      this.camera.distance = 35.0;
    }
    this.camera.yaw = 0.6;
    this.camera.pitch = 0.4;
  }

  reset() {
    this.frames = [];
    this.currentFrameIdx = 0;
    this.fractionalFrame = 0.0;
    this.isPlaying = false;
    this.isLiveFollowing = true;
    this.instanceCount = 0;
    this.runStats = {
      kinetic_energy: { min: Infinity, max: -Infinity },
      von_mises_stress: { min: Infinity, max: -Infinity }
    };
    if (this.options.onFrameChange) {
      this.options.onFrameChange(0, 0);
    }
    if (this.options.onTimestepChange) {
      this.options.onTimestepChange(0, false, 0, 0);
    }
  }

  _renderLoop(now) {
    requestAnimationFrame(this._renderLoop);

    if (this.isPlaying && this.frames.length > 1) {
      const dt = Math.min(0.1, (now - (this.lastRenderTime || now)) / 1000.0);
      this.lastRenderTime = now;

      this.fractionalFrame += this.playbackSpeed * dt;
      if (this.fractionalFrame >= this.frames.length - 1) {
        this.fractionalFrame = 0.0;
      }
      this.seek(this.fractionalFrame);
    } else {
      this.lastRenderTime = now;
    }

    this._draw();
  }

  _draw() {
    const gl = this.gl;
    if (!gl) return;

    this._resize();

    gl.enable(gl.DEPTH_TEST);
    gl.clearColor(0.04, 0.02, 0.08, 1.0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

    const aspect = this.canvas.width / Math.max(1, this.canvas.height);
    const proj = this._perspective(45 * Math.PI / 180, aspect, 0.1, 500.0);

    const cx = this.camera.target[0] + this.camera.distance * Math.cos(this.camera.pitch) * Math.sin(this.camera.yaw);
    const cy = this.camera.target[1] + this.camera.distance * Math.sin(this.camera.pitch);
    const cz = this.camera.target[2] + this.camera.distance * Math.cos(this.camera.pitch) * Math.cos(this.camera.yaw);
    const view = this._lookAt([cx, cy, cz], this.camera.target, [0, 1, 0]);

    // 1. Draw Bounding Box Wireframe with Depth-Appropriate Fading
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.useProgram(this.boxProgram);
    gl.uniformMatrix4fv(gl.getUniformLocation(this.boxProgram, "u_proj"), false, proj);
    gl.uniformMatrix4fv(gl.getUniformLocation(this.boxProgram, "u_view"), false, view);
    gl.bindVertexArray(this.boxVAO);
    gl.drawArrays(gl.LINES, 0, 24);
    gl.disable(gl.BLEND);

    // 2. Draw Instanced Atoms
    if (this.instanceCount > 0) {
      gl.useProgram(this.atomProgram);
      gl.uniformMatrix4fv(gl.getUniformLocation(this.atomProgram, "u_proj"), false, proj);
      gl.uniformMatrix4fv(gl.getUniformLocation(this.atomProgram, "u_view"), false, view);
      gl.uniform1i(gl.getUniformLocation(this.atomProgram, "u_colorMode"), (this.colorMode === "element" ? 0 : 1));
      gl.uniform1i(gl.getUniformLocation(this.atomProgram, "u_isInterpolated"), (this.isCurrentInterpolated ? 1 : 0));

      gl.bindVertexArray(this.atomVAO);
      gl.drawArraysInstanced(gl.TRIANGLES, 0, this.sphereVertexCount, this.instanceCount);
    }

    gl.bindVertexArray(null);
  }

  _perspective(fovy, aspect, near, far) {
    const f = 1.0 / Math.tan(fovy / 2);
    const nf = 1 / (near - far);
    return new Float32Array([
      f / aspect, 0, 0, 0,
      0, f, 0, 0,
      0, 0, (far + near) * nf, -1,
      0, 0, 2 * far * near * nf, 0
    ]);
  }

  _lookAt(eye, center, up) {
    let z0 = eye[0] - center[0], z1 = eye[1] - center[1], z2 = eye[2] - center[2];
    let len = 1 / Math.hypot(z0, z1, z2);
    z0 *= len; z1 *= len; z2 *= len;

    let x0 = up[1] * z2 - up[2] * z1;
    let x1 = up[2] * z0 - up[0] * z2;
    let x2 = up[0] * z1 - up[1] * z0;
    len = 1 / Math.hypot(x0, x1, x2);
    x0 *= len; x1 *= len; x2 *= len;

    let y0 = z1 * x2 - z2 * x1;
    let y1 = z2 * x0 - z0 * x2;
    let y2 = z0 * x1 - z1 * x0;

    return new Float32Array([
      x0, y0, z0, 0,
      x1, y1, z1, 0,
      x2, y2, z2, 0,
      -(x0 * eye[0] + x1 * eye[1] + x2 * eye[2]),
      -(y0 * eye[0] + y1 * eye[1] + y2 * eye[2]),
      -(z0 * eye[0] + z1 * eye[1] + z2 * eye[2]),
      1
    ]);
  }
}

window.TrajectoryViewer = TrajectoryViewer;
