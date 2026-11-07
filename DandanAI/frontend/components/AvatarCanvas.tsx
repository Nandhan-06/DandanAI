"use client";

import React, {
  forwardRef,
  useImperativeHandle,
  useEffect,
  useRef,
  useState,
} from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RefreshCw, Volume2, Sparkles, CheckCircle, Focus, PauseCircle, PlayCircle } from "lucide-react";
import { Badge, Button } from "@/components/ui";

export interface AvatarCanvasHandle {
  playAudioBlob: (blob: Blob) => Promise<void>;
  stopSpeaking: () => void;
  pauseSpeaking: () => void;
  resumeSpeaking: () => void;
  isSpeaking: () => boolean;
  isPaused: () => boolean;
}

interface AvatarCanvasProps {
  onTestVoice?: () => void;
  className?: string;
  audioElement?: any;
  isPlayingVoice?: boolean;
}

// Reduced mouth morph weights for natural lip movement
const MOUTH_TARGETS: Record<string, number> = {
  viseme_aa: 0.45,
  viseme_O: 0.40,
  viseme_U: 0.35,
  viseme_E: 0.35,
  viseme_I: 0.30,
  viseme_PP: 0.25,
  viseme_FF: 0.25,
  viseme_TH: 0.25,
  viseme_DD: 0.25,
  viseme_kk: 0.25,
  viseme_CH: 0.30,
  viseme_SS: 0.20,
  viseme_nn: 0.25,
  viseme_RR: 0.25,
  viseme_sil: 0.00,
  jawOpen: 0.40,
  mouthOpen: 0.35,
};

// IndexedDB to remember uploaded GLBs
const DB_NAME = "DandanAI_AvatarDB";
const STORE_NAME = "avatars";

async function saveGLBToDB(buffer: ArrayBuffer, fileName: string) {
  try {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(STORE_NAME);
    };
    req.onsuccess = () => {
      const db = req.result;
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).put({ buffer, fileName }, "user_glb");
    };
  } catch (e) {
    console.error("IndexedDB save failed", e);
  }
}

async function loadGLBFromDB(): Promise<{ buffer: ArrayBuffer; fileName: string } | null> {
  return new Promise((resolve) => {
    try {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => {
        req.result.createObjectStore(STORE_NAME);
      };
      req.onsuccess = () => {
        const db = req.result;
        const tx = db.transaction(STORE_NAME, "readonly");
        const getReq = tx.objectStore(STORE_NAME).get("user_glb");
        getReq.onsuccess = () => resolve(getReq.result || null);
        getReq.onerror = () => resolve(null);
      };
      req.onerror = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
}

async function clearGLBFromDB() {
  try {
    const req = indexedDB.open(DB_NAME, 1);
    req.onsuccess = () => {
      const db = req.result;
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).delete("user_glb");
    };
  } catch {}
}

export const AvatarCanvas = forwardRef<AvatarCanvasHandle, AvatarCanvasProps>(
  ({ onTestVoice, className }, ref) => {
    const hostRef = useRef<HTMLDivElement>(null);

    const [modelName, setModelName] = useState<string | null>(null);
    const [loadingModel, setLoadingModel] = useState(false);
    const [speakingState, setSpeakingState] = useState(false);
    const [pausedState, setPausedState] = useState(false);
    const [hasMorphs, setHasMorphs] = useState(true);

    // Three.js instances
    const sceneRef = useRef<THREE.Scene | null>(null);
    const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
    const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
    const controlsRef = useRef<OrbitControls | null>(null);
    const modelRef = useRef<THREE.Group | null>(null);
    const morphMeshesRef = useRef<THREE.Mesh[]>([]);
    const targetMapRef = useRef<Map<THREE.Mesh, { index: number; weight: number }[]>>(new Map());
    const jawBoneRef = useRef<THREE.Object3D | null>(null);
    const initialJawRotRef = useRef<number>(0);
    const baseYRef = useRef<number>(0);
    const focusTargetRef = useRef<THREE.Vector3>(new THREE.Vector3(0, 0, 0));
    const cameraDistRef = useRef<number>(0.8);

    // Web Audio instances
    const audioCtxRef = useRef<AudioContext | null>(null);
    const analyserRef = useRef<AnalyserNode | null>(null);
    const analyserDataRef = useRef<Uint8Array | null>(null);
    const currentAudioRef = useRef<HTMLAudioElement | null>(null);
    const speakingRef = useRef<boolean>(false);
    const pausedRef = useRef<boolean>(false);
    const mouthLevelRef = useRef<number>(0);

    // Ensure AudioContext and Analyser are ready
    const ensureAudio = () => {
      if (!audioCtxRef.current) {
        const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
        const ctx = new AudioCtx();
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 512;
        analyserRef.current = analyser;
        analyserDataRef.current = new Uint8Array(
  new ArrayBuffer(analyser.fftSize)
);
        analyser.connect(ctx.destination);
        audioCtxRef.current = ctx;
      }

      if (audioCtxRef.current.state === "suspended") {
        audioCtxRef.current.resume();
      }
    };

    // Calculate mouth level using RMS audio energy
    const readMouthLevel = () => {
      if (
        !speakingRef.current ||
        pausedRef.current ||
        !analyserRef.current ||
        !currentAudioRef.current ||
        !analyserDataRef.current
      ) {
        mouthLevelRef.current *= 0.8;
        if (mouthLevelRef.current < 0.001) mouthLevelRef.current = 0;
        return;
      }

      analyserRef.current.getByteTimeDomainData(analyserDataRef.current);

      let sum = 0;

      for (let i = 0; i < analyserDataRef.current.length; i++) {
        const v = (analyserDataRef.current[i] - 128) / 128;
        sum += v * v;
      }

      const rms = Math.sqrt(sum / analyserDataRef.current.length);

      // Reduced sensitivity and maximum mouth opening
      const target = Math.min(0.45, rms * 5);

      // Smooth audio response
      mouthLevelRef.current +=
        (target - mouthLevelRef.current) * 0.15;
    };

    // Expose control handles
    useImperativeHandle(ref, () => ({
      playAudioBlob: (blob: Blob) => {
        return new Promise<void>((resolve, reject) => {
          try {
            ensureAudio();

            const ctx = audioCtxRef.current!;
            const analyser = analyserRef.current!;

            // Stop previous audio
            if (currentAudioRef.current) {
              currentAudioRef.current.pause();
              currentAudioRef.current = null;
            }

            const url = URL.createObjectURL(blob);
            const audio = new Audio(url);
            currentAudioRef.current = audio;

            // Connect media element source to analyser
            try {
              const source = ctx.createMediaElementSource(audio);
              source.connect(analyser);
            } catch (err) {
              console.warn("createMediaElementSource fallback:", err);
            }

            speakingRef.current = true;
            setSpeakingState(true);

            audio.onended = () => {
              URL.revokeObjectURL(url);
              speakingRef.current = false;
              setSpeakingState(false);
              resolve();
            };

            audio.onerror = () => {
              URL.revokeObjectURL(url);
              speakingRef.current = false;
              setSpeakingState(false);
              reject(new Error("Audio playback failed."));
            };

            audio.play().catch((err) => {
              speakingRef.current = false;
              setSpeakingState(false);
              reject(err);
            });
          } catch (e) {
            speakingRef.current = false;
            setSpeakingState(false);
            reject(e);
          }
        });
      },

      stopSpeaking: () => {
        if (currentAudioRef.current) {
          currentAudioRef.current.pause();
          currentAudioRef.current = null;
        }

        speakingRef.current = false;
        pausedRef.current = false;
        setSpeakingState(false);
        setPausedState(false);
      },

      pauseSpeaking: () => {
        if (currentAudioRef.current && speakingRef.current && !pausedRef.current) {
          currentAudioRef.current.pause();
          pausedRef.current = true;
          setPausedState(true);
        }
      },

      resumeSpeaking: () => {
        if (currentAudioRef.current && speakingRef.current && pausedRef.current) {
          currentAudioRef.current.play().catch(() => {});
          pausedRef.current = false;
          setPausedState(false);
        }
      },

      isSpeaking: () => speakingRef.current,
      isPaused: () => pausedRef.current,
    }));

    // Setup Three.js scene and render loop
    useEffect(() => {
      const host = hostRef.current;
      if (!host) return;

      const w = host.clientWidth || 320;
      const h = host.clientHeight || 280;

      const renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
      });

      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setSize(w, h);
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.1;

      host.appendChild(renderer.domElement);
      rendererRef.current = renderer;

      const scene = new THREE.Scene();
      sceneRef.current = scene;

      const camera = new THREE.PerspectiveCamera(30, w / h, 0.01, 100);
      camera.position.set(0, 0, 1.2);
      cameraRef.current = camera;

      const controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.05;
      controls.maxPolarAngle = Math.PI * 0.7;
      controls.minPolarAngle = Math.PI * 0.2;
      controlsRef.current = controls;

      // Lighting
      scene.add(new THREE.HemisphereLight(0xffffff, 0x8899bb, 1.4));

      const key = new THREE.DirectionalLight(0xffffff, 1.6);
      key.position.set(1.5, 2, 3);
      scene.add(key);

      const fill = new THREE.DirectionalLight(0x93c5fd, 0.6);
      fill.position.set(-1.5, 1, 1.5);
      scene.add(fill);

      // Handle Resize
      const resizeObserver = new ResizeObserver(() => {
        if (!host || !renderer || !camera) return;

        const width = host.clientWidth;
        const height = host.clientHeight;

        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height);
      });

      resizeObserver.observe(host);

      // Animation loop
      let animId: number;

      const tick = (time: number) => {
        animId = requestAnimationFrame(tick);

        readMouthLevel();

        const t = time / 1000;
        const model = modelRef.current;
        const mouthLevel = mouthLevelRef.current;

        if (renderer && scene && camera && model) {
          // 1. Apply smooth mouth morph targets
          for (const mesh of morphMeshesRef.current) {
            const targets = targetMapRef.current.get(mesh);

            if (targets && mesh.morphTargetInfluences) {
              for (const { index, weight } of targets) {
                const current = mesh.morphTargetInfluences[index];
                const target = mouthLevel * weight;

                mesh.morphTargetInfluences[index] =
                  THREE.MathUtils.lerp(current, target, 0.15);
              }
            }
          }

          // 2. Apply reduced jaw movement
          if (jawBoneRef.current) {
            jawBoneRef.current.rotation.x =
              initialJawRotRef.current + mouthLevel * 0.08;
          }

          // 3. Body language and speaking animation
          const rotY = Math.sin(t * 0.6) * 0.05;
          let rotZ = 0;
          let bob = Math.sin(t * 1.5) * 0.002;

          if (speakingRef.current) {
            bob = Math.sin(t * 8) * 0.003 + mouthLevel * 0.004;
          }

          model.rotation.y += (rotY - model.rotation.y) * 0.1;
          model.rotation.z += (rotZ - model.rotation.z) * 0.1;
          model.position.y = baseYRef.current + bob;

          controls.update();
          renderer.render(scene, camera);
        }
      };

      requestAnimationFrame(tick);

      // Load saved GLB or default avatar
      loadGLBFromDB().then((saved) => {
        if (saved) {
          parseAndMountGLB(saved.buffer, saved.fileName);
        } else {
          loadGlbFromUrl("/avatar-default.glb", "Default Avatar");
        }
      });

      return () => {
        cancelAnimationFrame(animId);
        resizeObserver.disconnect();

        if (renderer.domElement && host.contains(renderer.domElement)) {
          host.removeChild(renderer.domElement);
        }

        renderer.dispose();
      };
    }, []);

    // Camera recenter to head and shoulders
    const recenterHead = () => {
      const camera = cameraRef.current;
      const controls = controlsRef.current;

      if (!camera || !controls) return;

      const target = focusTargetRef.current;
      const dist = cameraDistRef.current;

      camera.position.set(target.x, target.y, target.z + dist);
      camera.lookAt(target);
      controls.target.copy(target);
      controls.minDistance = Math.max(0.2, dist * 0.5);
      controls.maxDistance = Math.max(1.0, dist * 2.2);
      controls.update();
    };

    // Frame model head and setup morph targets
    const setupModelInScene = (model: THREE.Group, fileName: string) => {
      const scene = sceneRef.current;
      const camera = cameraRef.current;
      const controls = controlsRef.current;

      if (!scene || !camera || !controls) return;

      // Remove previous model
      if (modelRef.current) {
        scene.remove(modelRef.current);
        modelRef.current = null;
      }

      morphMeshesRef.current = [];
      targetMapRef.current.clear();
      jawBoneRef.current = null;

      // Discover morph meshes and jaw bone
      model.traverse((o: any) => {
        if (o.isBone || o.isObject3D) {
          if (!jawBoneRef.current && o.name && /jaw/i.test(o.name)) {
            jawBoneRef.current = o;
            initialJawRotRef.current = o.rotation.x;
          }
        }

        // Skip eye meshes
        if (o.isMesh && /eye/i.test(o.name || "")) return;

        if (o.isMesh && o.morphTargetDictionary && o.morphTargetInfluences) {
          morphMeshesRef.current.push(o);

          const list: { index: number; weight: number }[] = [];

          for (const [targetName, weight] of Object.entries(MOUTH_TARGETS)) {
            let idx = o.morphTargetDictionary[targetName];

            if (idx === undefined) {
              const lower = targetName.toLowerCase();

              for (const [meshKey, meshIdx] of Object.entries(o.morphTargetDictionary)) {
                if (meshKey.toLowerCase() === lower) {
                  idx = meshIdx as number;
                  break;
                }
              }
            }

            if (idx !== undefined) {
              list.push({ index: idx, weight });
            }
          }

          if (list.length > 0) {
            targetMapRef.current.set(o, list);
          }
        }
      });

      setHasMorphs(morphMeshesRef.current.length > 0);

      scene.add(model);
      modelRef.current = model;

      // Camera framing
      const box = new THREE.Box3().setFromObject(model);
      const size = box.getSize(new THREE.Vector3());
      const center = box.getCenter(new THREE.Vector3());
      const upper = morphMeshesRef.current.length > 0;

      const focusY = upper ? box.max.y - size.y * 0.13 : center.y;
      const span = upper ? size.y * 0.3 : Math.max(size.x, size.y);

      const dist =
        (span / 2) /
        Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) *
        1.25;

      focusTargetRef.current.set(center.x, focusY, center.z);
      cameraDistRef.current = dist + size.z / 2;
      baseYRef.current = model.position.y;

      recenterHead();
      setModelName(fileName);
      setLoadingModel(false);
    };

    // Load from ArrayBuffer
    const parseAndMountGLB = (buffer: ArrayBuffer, fileName: string) => {
      setLoadingModel(true);

      new GLTFLoader().parse(
        buffer,
        "",
        (gltf) => {
          setupModelInScene(gltf.scene, fileName);
        },
        (err) => {
          console.error("GLB parse error:", err);
          setLoadingModel(false);
          alert("Could not load that .glb model.");
        }
      );
    };

    // Load from URL
    const loadGlbFromUrl = (url: string, fileName: string) => {
      setLoadingModel(true);

      new GLTFLoader().load(
        url,
        (gltf) => {
          setupModelInScene(gltf.scene, fileName);
        },
        undefined,
        (err) => {
          console.warn("Could not load default GLB:", err);
          setLoadingModel(false);
        }
      );
    };

    // Handle user uploading custom GLB
    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;

      if (!file.name.toLowerCase().endsWith(".glb")) {
        alert("Please upload a .glb model.");
        return;
      }

      try {
        const buffer = await file.arrayBuffer();
        parseAndMountGLB(buffer, file.name);
        saveGLBToDB(buffer, file.name);
      } catch (err) {
        console.error("Upload error", err);
      }
    };

    // Reset back to default
    const handleReset = async () => {
      await clearGLBFromDB();
      loadGlbFromUrl("/avatar-default.glb", "Default Avatar");
    };

    return (
      <div
        className={`relative overflow-hidden rounded-xl border border-ink-200 bg-gradient-to-b from-ink-50/70 to-ink-100/40 p-3 shadow-inner ${
          className || ""
        }`}
      >
        {/* Header bar with Status and Upload controls */}
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-ink-700">
              3D Avatar
            </span>

            {modelName ? (
              <Badge tone="blue" className="max-w-[160px] truncate">
                <CheckCircle className="mr-1 h-3 w-3 inline text-brand-600" />
                {modelName}
              </Badge>
            ) : (
              <Badge tone="gray">3D Avatar</Badge>
            )}

            {/* Speaking / idle indicator */}
            {speakingState ? (
              <span className="flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800 animate-pulse">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                {pausedState ? "Paused" : "Speaking (Mouth Moving)"}
              </span>
            ) : (
              <span className="flex items-center gap-1 rounded-full bg-ink-100 px-2 py-0.5 text-[11px] text-ink-600">
                <span className="h-2 w-2 rounded-full bg-ink-400" />
                Mouth Idle (No Voice)
              </span>
            )}
          </div>

          <div className="flex items-center gap-1.5">
            {/* Pause / Resume button — only shown while avatar is speaking */}
            {speakingState && (
              <Button
                variant="outline"
                size="sm"
                className="!px-2 !py-1 text-xs"
                onClick={() => {
                  if (pausedState) {
                    currentAudioRef.current?.play().catch(() => {});
                    pausedRef.current = false;
                    setPausedState(false);
                  } else {
                    currentAudioRef.current?.pause();
                    pausedRef.current = true;
                    setPausedState(true);
                  }
                }}
                title={pausedState ? "Resume speaking" : "Pause speaking"}
              >
                {pausedState ? (
                  <PlayCircle className="h-3.5 w-3.5 text-brand-600" />
                ) : (
                  <PauseCircle className="h-3.5 w-3.5 text-amber-600" />
                )}
                {pausedState ? "Resume" : "Pause"}
              </Button>
            )}

            <Button
              variant="ghost"
              size="sm"
              className="!px-1.5 !py-1 text-xs"
              onClick={recenterHead}
              title="Re-center camera to head"
            >
              <Focus className="h-3.5 w-3.5" />
            </Button>

            {onTestVoice && (
              <Button
                variant="outline"
                size="sm"
                className="!px-2 !py-1 text-xs"
                onClick={onTestVoice}
                title="Test Edge TTS Liam voice with mouth lip sync"
              >
                <Volume2 className="h-3.5 w-3.5 text-brand-600" />
                Test Voice
              </Button>
            )}
          </div>
        </div>

        {/* Three.js Canvas Container */}
        <div
          ref={hostRef}
          className="relative h-64 w-full cursor-grab overflow-hidden rounded-lg bg-gradient-to-b from-sky-50/50 to-brand-50/40 active:cursor-grabbing sm:h-72"
          title="Drag to inspect, scroll to zoom (frames head portion)"
        >
          {loadingModel && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/70 backdrop-blur-sm text-xs font-medium text-ink-700">
              <RefreshCw className="mr-2 h-4 w-4 animate-spin text-brand-600" />
              Loading avatar model…
            </div>
          )}

          {/* Lip sync status badge */}
          <div className="pointer-events-none absolute bottom-2 left-2 flex items-center gap-1 rounded bg-white/80 px-2 py-0.5 text-[10px] text-ink-500 backdrop-blur-sm">
            <Sparkles className="h-3 w-3 text-brand-500" />
            {hasMorphs
              ? "Audio Lip-Sync: Blend shapes active"
              : "Avatar loaded (speaking nod active)"}
          </div>
        </div>

        <p className="mt-1.5 text-center text-[11px] text-ink-500">
          Head framed automatically • Mouth moves when voice speaks, stays motionless when silent
        </p>
      </div>
    );
  }
);

AvatarCanvas.displayName = "AvatarCanvas";