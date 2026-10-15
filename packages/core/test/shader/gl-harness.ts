// Browser-side executor for the shader parity test. `renderScenes` is serialised by Playwright and run
// INSIDE headless Chromium, so it must be self-contained plain JS (no imports, no closures, no TS-only
// syntax). It compiles the program once, binds uniforms by the type table, renders each scene and reads
// the pixels back top-down (readPixels is bottom-up). Never fakes pixels: any GL failure throws.

export interface SceneIn { w: number; h: number; uniforms: Record<string, number | number[]> }
export interface HarnessIn {
  vs: string;
  fs: string;
  types: Record<string, string>;
  scenes: SceneIn[];
  bench: { w: number; h: number; frames: number; uniforms: Record<string, number | number[]> } | null;
}
export interface HarnessOut { pixels: string[]; renderer: string; version: string; benchMsPerFrame: number | null }

export function renderScenes(input: HarnessIn): HarnessOut {
  const canvas = document.createElement('canvas');
  const gl = canvas.getContext('webgl2', { preserveDrawingBuffer: true, antialias: false, alpha: true });
  if (!gl) throw new Error('webgl2 context unavailable');
  const compile = (type: number, src: string): WebGLShader => {
    const sh = gl.createShader(type)!;
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error('compile: ' + gl.getShaderInfoLog(sh));
    return sh;
  };
  const prog = gl.createProgram()!;
  gl.attachShader(prog, compile(gl.VERTEX_SHADER, input.vs));
  gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, input.fs));
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error('link: ' + gl.getProgramInfoLog(prog));
  gl.useProgram(prog);

  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, 'aPos');
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

  const bind = (u: Record<string, number | number[]>): void => {
    for (const name of Object.keys(input.types)) {
      const where = gl.getUniformLocation(prog, name);
      if (where === null) throw new Error('uniform not active in program: ' + name);
      const v = u[name];
      if (v === undefined) throw new Error('uniform not supplied: ' + name);
      const t = input.types[name];
      if (t === 'i') gl.uniform1i(where, v as number);
      else if (t === 'f') gl.uniform1f(where, v as number);
      else if (t === '2f') gl.uniform2fv(where, v as number[]);
      else if (t === '3f') gl.uniform3fv(where, v as number[]);
      else if (t === '3fv') gl.uniform3fv(where, v as number[]);
      else throw new Error('unknown uniform type ' + t);
    }
  };
  const draw = (w: number, h: number, u: Record<string, number | number[]>): void => {
    canvas.width = w;
    canvas.height = h;
    gl.viewport(0, 0, w, h);
    bind(u);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  };
  const b64 = (bytes: Uint8Array): string => {
    let s = '';
    for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + 0x8000)));
    return btoa(s);
  };

  const pixels: string[] = [];
  for (const sc of input.scenes) {
    draw(sc.w, sc.h, sc.uniforms);
    const raw = new Uint8Array(sc.w * sc.h * 4);
    gl.readPixels(0, 0, sc.w, sc.h, gl.RGBA, gl.UNSIGNED_BYTE, raw);
    const top = new Uint8Array(raw.length);
    for (let y = 0; y < sc.h; y++) top.set(raw.subarray((sc.h - 1 - y) * sc.w * 4, (sc.h - y) * sc.w * 4), y * sc.w * 4);
    pixels.push(b64(top));
  }

  let benchMsPerFrame: number | null = null;
  if (input.bench) {
    const one = new Uint8Array(4);
    const frame = (): void => { draw(input.bench!.w, input.bench!.h, input.bench!.uniforms); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, one); };
    for (let i = 0; i < 3; i++) frame();                     // warm up (shader JIT)
    const t0 = performance.now();
    for (let i = 0; i < input.bench.frames; i++) frame();
    benchMsPerFrame = (performance.now() - t0) / input.bench.frames;
  }
  const dbg = gl.getExtension('WEBGL_debug_renderer_info');
  return {
    pixels,
    renderer: dbg ? String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL)) : String(gl.getParameter(gl.RENDERER)),
    version: String(gl.getParameter(gl.VERSION)),
    benchMsPerFrame,
  };
}
