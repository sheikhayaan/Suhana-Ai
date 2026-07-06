import React, { useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion';
import { ArrowRight, Search, Sparkles, Code2, GraduationCap, Film, FileText } from 'lucide-react';
import * as THREE from 'three';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import './suhana-hero.css';

gsap.registerPlugin(ScrollTrigger);

const phrases = [
  'generate viral reels',
  'study any concept',
  'solve DSA problems',
  'create AI images',
  'edit PDFs faster',
  'plan creator brands'
];

const tools = [
  ['Reel Generator', Film],
  ['AI Tutor', GraduationCap],
  ['Suhana Code', Code2],
  ['PDF + Image Tools', FileText]
];

const fruitNodes = [
  ['Reels', 'Script + voice + MP4', 0.18, 0xfff3b0],
  ['Tutor', 'Lessons + quizzes', 0.34, 0x7dd3fc],
  ['Code', 'DSA + debugging', 0.48, 0xb9a7ff],
  ['Visuals', 'Images + storyboards', 0.6, 0x47ffd0],
  ['PDF', 'Merge + compress', 0.72, 0xff8cc6],
  ['Brand', 'Memory + planning', 0.84, 0xffffff]
];

function makeNebulaTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 128;
  canvas.height = 128;
  const ctx = canvas.getContext('2d');
  const gradient = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  gradient.addColorStop(0, 'rgba(255,255,255,1)');
  gradient.addColorStop(0.22, 'rgba(125,211,252,.8)');
  gradient.addColorStop(0.54, 'rgba(52,211,153,.24)');
  gradient.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(canvas);
}

function useHeroWebgl(mountRef) {
  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
    camera.position.set(0, 0.2, 8.4);

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'high-performance' });
    renderer.setClearColor(0x000000, 0);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.8));
    mount.appendChild(renderer.domElement);

    const pointer = { x: 0, y: 0 };
    const rig = new THREE.Group();
    scene.add(rig);

    const coreMaterial = new THREE.MeshPhysicalMaterial({
      color: 0x9be7ff,
      emissive: 0x164f62,
      roughness: 0.22,
      metalness: 0.08,
      transmission: 0.18,
      thickness: 1.4,
      transparent: true,
      opacity: 0.92
    });
    const core = new THREE.Mesh(new THREE.IcosahedronGeometry(1.18, 8), coreMaterial);
    core.scale.setScalar(0.34);
    core.position.y = -0.52;
    rig.add(core);

    const wire = new THREE.Mesh(
      new THREE.IcosahedronGeometry(1.62, 2),
      new THREE.MeshBasicMaterial({ color: 0xffffff, wireframe: true, transparent: true, opacity: 0.16 })
    );
    wire.scale.setScalar(0.52);
    wire.position.y = -0.52;
    rig.add(wire);

    const rings = [];

    const texture = makeNebulaTexture();
    const vortex = new THREE.Group();
    rig.add(vortex);

    const particleCount = 3600;
    const positions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);
    const colorPool = [new THREE.Color(0xdff7ff), new THREE.Color(0x7dd3fc), new THREE.Color(0x47ffd0), new THREE.Color(0xb9a7ff)];
    for (let i = 0; i < particleCount; i += 1) {
      const t = i / particleCount;
      const y = -3.05 + t * 6.25;
      const treeBulge = Math.sin(t * Math.PI);
      const taper = 0.16 + Math.pow(t, 1.12) * 2.55 + treeBulge * 0.75;
      const branchNoise = Math.sin(t * 44) * 0.16 + Math.sin(t * 91) * 0.08;
      const radius = Math.max(0.08, taper + branchNoise) * (0.62 + Math.random() * 0.56);
      const twist = t * Math.PI * 22 + Math.sin(t * 9) * 1.8 + Math.random() * 0.34;
      const flare = t > 0.72 ? (t - 0.72) * 2.1 : 0;
      positions[i * 3] = Math.cos(twist) * (radius + flare);
      positions[i * 3 + 1] = y + (Math.random() - 0.5) * 0.22;
      positions[i * 3 + 2] = Math.sin(twist) * (radius + flare) * 0.78;
      const c = colorPool[Math.floor(Math.random() * colorPool.length)];
      colors[i * 3] = c.r;
      colors[i * 3 + 1] = c.g;
      colors[i * 3 + 2] = c.b;
    }
    const particleGeo = new THREE.BufferGeometry();
    particleGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    particleGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    const particles = new THREE.Points(
      particleGeo,
      new THREE.PointsMaterial({
        size: 0.048,
        map: texture,
        vertexColors: true,
        transparent: true,
        opacity: 0.86,
        depthWrite: false,
        blending: THREE.AdditiveBlending
      })
    );
    vortex.add(particles);

    const spiralLines = [];
    for (let lineIndex = 0; lineIndex < 9; lineIndex += 1) {
      const linePoints = [];
      for (let s = 0; s < 320; s += 1) {
        const t = s / 319;
        const y = -3.08 + t * 6.18;
        const radius = 0.2 + Math.pow(t, 1.08) * 2.52 + Math.sin(t * Math.PI) * 0.52;
        const angle = t * Math.PI * 12 + lineIndex * 0.7;
        linePoints.push(new THREE.Vector3(Math.cos(angle) * radius, y, Math.sin(angle) * radius * 0.76));
      }
      const curve = new THREE.CatmullRomCurve3(linePoints);
      const lineGeo = new THREE.BufferGeometry().setFromPoints(curve.getPoints(440));
      const line = new THREE.Line(
        lineGeo,
        new THREE.LineBasicMaterial({
          color: lineIndex % 3 === 0 ? 0xffffff : lineIndex % 3 === 1 ? 0x47ffd0 : 0x7dd3fc,
          transparent: true,
          opacity: lineIndex % 3 === 0 ? 0.18 : 0.13,
          blending: THREE.AdditiveBlending
        })
      );
      spiralLines.push(line);
      vortex.add(line);
    }

    const rootGeo = new THREE.BufferGeometry();
    const rootPositions = [];
    for (let i = 0; i < 42; i += 1) {
      const angle = (i / 42) * Math.PI * 2;
      rootPositions.push(0, -3.05, 0);
      rootPositions.push(Math.cos(angle) * (1.3 + Math.random() * 1.9), -3.52 - Math.random() * 0.26, Math.sin(angle) * (0.8 + Math.random() * 1.2));
    }
    rootGeo.setAttribute('position', new THREE.Float32BufferAttribute(rootPositions, 3));
    const roots = new THREE.LineSegments(
      rootGeo,
      new THREE.LineBasicMaterial({ color: 0x7dd3fc, transparent: true, opacity: 0.16, blending: THREE.AdditiveBlending })
    );
    vortex.add(roots);

    const fruitGroup = new THREE.Group();
    vortex.add(fruitGroup);
    const fruitMeshes = [];
    const branchMaterial = new THREE.LineBasicMaterial({
      color: 0xdff7ff,
      transparent: true,
      opacity: 0.22,
      blending: THREE.AdditiveBlending
    });
    fruitNodes.forEach(([label, detail, t, color], index) => {
      const y = -3.05 + t * 6.25;
      const side = index % 2 === 0 ? 1 : -1;
      const angle = t * Math.PI * 22 + index * 0.86;
      const branchRadius = 0.5 + Math.pow(t, 1.08) * 2.45 + Math.sin(t * Math.PI) * 0.58;
      const anchor = new THREE.Vector3(
        Math.cos(angle) * branchRadius,
        y,
        Math.sin(angle) * branchRadius * 0.76
      );
      const fruitPosition = new THREE.Vector3(
        anchor.x + side * (0.48 + index * 0.05),
        anchor.y + 0.16 + Math.sin(index) * 0.12,
        anchor.z + (index % 3 - 1) * 0.26
      );
      const fruit = new THREE.Mesh(
        new THREE.SphereGeometry(0.16 + (index % 3) * 0.018, 28, 28),
        new THREE.MeshPhysicalMaterial({
          color,
          emissive: color,
          emissiveIntensity: 0.55,
          roughness: 0.18,
          metalness: 0.08,
          transmission: 0.12,
          thickness: 0.8,
          transparent: true,
          opacity: 0.92
        })
      );
      fruit.position.copy(fruitPosition);
      fruit.userData = { label, detail, index };
      fruitGroup.add(fruit);
      fruitMeshes.push(fruit);

      const stemGeo = new THREE.BufferGeometry().setFromPoints([anchor, fruitPosition]);
      const stem = new THREE.Line(stemGeo, branchMaterial.clone());
      fruitGroup.add(stem);

      const halo = new THREE.Mesh(
        new THREE.RingGeometry(0.22, 0.225, 42),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.36, side: THREE.DoubleSide, blending: THREE.AdditiveBlending })
      );
      halo.position.copy(fruitPosition);
      halo.rotation.x = Math.PI * 0.5;
      fruitGroup.add(halo);
      fruitMeshes.push(halo);
    });

    scene.add(new THREE.AmbientLight(0xffffff, 1.4));
    const cyan = new THREE.PointLight(0x7dd3fc, 5, 12);
    cyan.position.set(-3, 2.6, 4);
    scene.add(cyan);
    const green = new THREE.PointLight(0x34d399, 4, 12);
    green.position.set(3, -1.6, 3);
    scene.add(green);

    const intro = gsap.timeline({ defaults: { ease: 'expo.out' } });
    intro.fromTo(rig.scale, { x: 0.42, y: 0.42, z: 0.42 }, { x: 1, y: 1, z: 1, duration: 1.9 });
    intro.fromTo(core.rotation, { x: -1.2, y: 0.8 }, { x: 0.2, y: 0, duration: 1.7 }, '<');
    intro.fromTo(renderer.domElement, { opacity: 0, filter: 'blur(22px)' }, { opacity: 1, filter: 'blur(0px)', duration: 1.2 }, '<');
    intro.fromTo(vortex.rotation, { y: -1.6 }, { y: 0, duration: 2.1 }, '<');
    intro.fromTo(fruitGroup.scale, { x: 0.2, y: 0.2, z: 0.2 }, { x: 1, y: 1, z: 1, duration: 1.6 }, '-=1.1');

    const scrollTween = gsap.to(vortex.rotation, {
      y: Math.PI * 1.35,
      x: -0.28,
      ease: 'none',
      scrollTrigger: {
        trigger: '.hero',
        start: 'top top',
        end: 'bottom top',
        scrub: 0.8
      }
    });

    const scrollScale = gsap.to(vortex.scale, {
      x: 1.18,
      y: 1.18,
      z: 1.18,
      ease: 'none',
      scrollTrigger: {
        trigger: '.hero',
        start: 'top top',
        end: 'bottom top',
        scrub: 0.8
      }
    });

    const onPointer = (event) => {
      const rect = mount.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / Math.max(1, rect.width) - 0.5) * 2;
      pointer.y = ((event.clientY - rect.top) / Math.max(1, rect.height) - 0.5) * 2;
    };
    mount.addEventListener('pointermove', onPointer, { passive: true });

    const resize = () => {
      const rect = mount.getBoundingClientRect();
      const width = Math.max(1, rect.width);
      const height = Math.max(1, rect.height);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    resize();
    window.addEventListener('resize', resize, { passive: true });

    let frameId = 0;
    const render = (timeMs) => {
      const time = timeMs * 0.001;
      rig.rotation.y += (pointer.x * 0.18 - rig.rotation.y) * 0.035;
      rig.rotation.x += (-pointer.y * 0.1 - rig.rotation.x) * 0.035;
      core.rotation.x = time * 0.31;
      core.rotation.y = time * 0.42;
      wire.rotation.y = -time * 0.18;
      vortex.rotation.y += 0.0038;
      spiralLines.forEach((line, index) => {
        line.material.opacity = 0.1 + Math.sin(time * 1.3 + index) * 0.035;
      });
      particles.rotation.y = time * 0.028;
      particles.rotation.x = Math.sin(time * 0.28) * 0.045;
      fruitMeshes.forEach((mesh, index) => {
        mesh.rotation.y = time * (0.8 + index * 0.02);
        mesh.position.y += Math.sin(time * 1.4 + index) * 0.0009;
        if (mesh.material) {
          mesh.material.opacity = 0.58 + Math.sin(time * 1.8 + index) * 0.12;
        }
      });
      renderer.render(scene, camera);
      frameId = requestAnimationFrame(render);
    };
    frameId = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(frameId);
      window.removeEventListener('resize', resize);
      mount.removeEventListener('pointermove', onPointer);
      intro.kill();
      scrollTween.kill();
      scrollScale.kill();
      particleGeo.dispose();
      spiralLines.forEach((line) => {
        line.geometry.dispose();
        line.material.dispose();
      });
      fruitGroup.traverse((obj) => {
        if (obj.geometry) obj.geometry.dispose();
        if (obj.material) obj.material.dispose();
      });
      rootGeo.dispose();
      texture.dispose();
      renderer.dispose();
      mount.innerHTML = '';
    };
  }, [mountRef]);
}

function MagneticStage() {
  const ref = useRef(null);
  const mx = useMotionValue(0);
  const my = useMotionValue(0);
  const sx = useSpring(mx, { stiffness: 80, damping: 18, mass: 0.4 });
  const sy = useSpring(my, { stiffness: 80, damping: 18, mass: 0.4 });
  const rotateY = useTransform(sx, [-1, 1], [-14, 14]);
  const rotateX = useTransform(sy, [-1, 1], [10, -10]);

  return (
    <motion.div
      ref={ref}
      className="suhana-magnet"
      style={{ rotateX, rotateY }}
      onPointerMove={(event) => {
        const box = ref.current?.getBoundingClientRect();
        if (!box) return;
        mx.set(((event.clientX - box.left) / box.width - 0.5) * 2);
        my.set(((event.clientY - box.top) / box.height - 0.5) * 2);
      }}
      onPointerLeave={() => {
        mx.set(0);
        my.set(0);
      }}
    >
      <div className="suhana-orbit-ring ring-one" />
      <div className="suhana-orbit-ring ring-two" />
      <div className="suhana-orbit-ring ring-three" />
      <div className="suhana-core">
        <span>S</span>
      </div>
      <div className="suhana-node node-a">REELS</div>
      <div className="suhana-node node-b">TUTOR</div>
      <div className="suhana-node node-c">CODE</div>
    </motion.div>
  );
}

function SuhanaHero() {
  const webglRef = useRef(null);
  useHeroWebgl(webglRef);

  useEffect(() => {
    document.body.classList.add('react-hero-mounted');
    document.body.classList.add('active-theory-mode');
    const items = gsap.utils.toArray('.scroll-reveal, .start-card, .bento-tile, .story-card, .flagship-card, .stat-box');
    items.forEach((item, index) => {
      gsap.fromTo(item, {
        y: 120,
        opacity: 0,
        filter: 'blur(18px)'
      }, {
        y: 0,
        opacity: 1,
        filter: 'blur(0px)',
        duration: 1.1,
        delay: (index % 3) * 0.04,
        ease: 'expo.out',
        scrollTrigger: {
          trigger: item,
          start: 'top 88%',
          end: 'top 44%',
          scrub: 0.4
        }
      });
    });
    gsap.to('.hero .suhana-giant-title', {
      yPercent: -22,
      opacity: 0.24,
      filter: 'blur(10px)',
      ease: 'none',
      scrollTrigger: {
        trigger: '.hero',
        start: 'top top',
        end: 'bottom top',
        scrub: true
      }
    });
    return () => {
      ScrollTrigger.getAll().forEach((trigger) => trigger.kill());
      document.body.classList.remove('react-hero-mounted');
      document.body.classList.remove('active-theory-mode');
    };
  }, []);

  return (
    <section className="suhana-react-hero" aria-label="Suhana AI hero">
      <div className="suhana-webgl-stage" ref={webglRef} aria-hidden="true" />
      <div className="suhana-scan-field" aria-hidden="true" />
      <motion.div
        className="suhana-topline suhana-theory-topline"
        initial={{ opacity: 0, y: -18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
      >
        <a href="/" className="suhana-brand-pill">
          <Sparkles size={15} />
          <span>Suhana AI</span>
        </a>
        <div className="suhana-nav-pill">
          <a href="/tools">Tools</a>
          <a href="/ai-tutor">Tutor</a>
          <a href="/suhana-code">Code</a>
          <a href="/dashboard">Dashboard</a>
        </div>
        <a href="/signup" className="suhana-start-pill">Login / Start</a>
      </motion.div>

      <motion.h1
        className="suhana-giant-title"
        initial={{ opacity: 0, y: 46, filter: 'blur(18px)' }}
        animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
        transition={{ duration: 0.9, delay: 0.12, ease: [0.16, 1, 0.3, 1] }}
      >
        SUHANA
      </motion.h1>

      <motion.div
        className="suhana-feature-tree"
        initial={{ opacity: 0, scale: 0.72, filter: 'blur(18px)' }}
        animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
        transition={{ duration: 1.2, delay: 0.25, ease: [0.16, 1, 0.3, 1] }}
        aria-label="Suhana AI feature tree"
      >
        <svg className="feature-tree-lines" viewBox="0 0 900 760" aria-hidden="true">
          <defs>
            <linearGradient id="treeGlow" x1="0" x2="1">
              <stop offset="0%" stopColor="#7dd3fc" />
              <stop offset="48%" stopColor="#47ffd0" />
              <stop offset="100%" stopColor="#ffffff" />
            </linearGradient>
            <filter id="treeBlur">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <path className="tree-trunk trunk-a" d="M451 720 C384 596 520 510 432 404 C352 306 518 238 449 76" />
          <path className="tree-trunk trunk-b" d="M449 720 C530 590 383 500 472 390 C548 296 386 220 455 76" />
          <path className="tree-spiral" d="M270 646 C590 720 700 520 470 456 C210 384 276 170 608 190" />
          <path className="tree-spiral second" d="M646 620 C302 660 178 438 440 372 C704 306 612 104 296 152" />
          <path className="tree-branch" d="M444 554 C340 510 286 464 204 406" />
          <path className="tree-branch" d="M468 515 C578 472 640 422 724 356" />
          <path className="tree-branch" d="M430 398 C316 360 250 300 176 226" />
          <path className="tree-branch" d="M478 378 C594 332 664 270 744 202" />
          <path className="tree-branch" d="M448 270 C390 226 340 178 276 112" />
          <path className="tree-branch" d="M466 260 C548 210 604 158 668 98" />
          <g className="tree-roots">
            <path d="M450 704 C390 735 330 748 250 742" />
            <path d="M452 704 C520 738 586 746 676 730" />
            <path d="M450 704 C426 744 386 764 312 782" />
            <path d="M452 704 C480 744 524 764 610 780" />
          </g>
        </svg>

        {fruitNodes.map(([label, detail], index) => (
          <a className={`tree-fruit tree-fruit-${index + 1}`} href="/tools" key={label}>
            <i />
            <span>{label}</span>
            <small>{detail}</small>
          </a>
        ))}
      </motion.div>

      <motion.div
        className="suhana-hero-caption caption-left"
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.75, delay: 0.46, ease: [0.16, 1, 0.3, 1] }}
      >
        <span>AI WORLD</span>
        <b>Creator tools, learning systems, code help, documents, visuals, and reels inside one moving interface.</b>
      </motion.div>

      <motion.div
        className="suhana-hero-caption caption-right"
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.75, delay: 0.52, ease: [0.16, 1, 0.3, 1] }}
      >
        <span>LIVE STACK</span>
        <b>Three.js / GSAP / Vite / Flask</b>
      </motion.div>

      <div className="suhana-fruit-labels" aria-hidden="true">
        {fruitNodes.map(([label, detail], index) => (
          <div className={`fruit-label fruit-${index + 1}`} key={label}>
            <span>{String(index + 1).padStart(2, '0')}</span>
            <b>{label}</b>
            <small>{detail}</small>
          </div>
        ))}
      </div>

      <motion.div
        className="suhana-stage-wrap"
        initial={{ opacity: 0, y: 40, scale: 0.94 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.9, delay: 0.35, ease: [0.16, 1, 0.3, 1] }}
      >
        <MagneticStage />
      </motion.div>

      <motion.p
        className="suhana-left-copy"
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.75, delay: 0.5, ease: [0.16, 1, 0.3, 1] }}
      >
        Create reels, write scripts, learn faster, solve code, edit images, merge PDFs, plan brands, and manage your AI workflow from one premium control room.
      </motion.p>

      <motion.div
        className="suhana-type-stack"
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.75, delay: 0.58, ease: [0.16, 1, 0.3, 1] }}
      >
        <span>One workspace to</span>
        <div className="suhana-css-type">
          {phrases.map((phrase, index) => (
            <b key={phrase} style={{ '--delay': `${index * 3}s`, '--width': `${phrase.length + 1}ch` }}>
              {phrase}
            </b>
          ))}
        </div>
      </motion.div>

      <motion.form
        className="suhana-search"
        action="/tools"
        method="get"
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.75, delay: 0.66, ease: [0.16, 1, 0.3, 1] }}
      >
        <Search size={18} />
        <input name="q" placeholder="Search tools, ideas, scripts, lessons..." aria-label="Search Suhana AI tools" />
        <button type="submit">Explore <ArrowRight size={17} /></button>
      </motion.form>

      <motion.div
        className="suhana-action-row"
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.75, delay: 0.74, ease: [0.16, 1, 0.3, 1] }}
      >
        <a href="/create">Start Creating</a>
        <a href="/tools">Open Tools</a>
        <a href="/signup">Join Suhana AI</a>
      </motion.div>

      <motion.div
        className="suhana-scroll-rail"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.9, delay: 1 }}
        aria-hidden="true"
      >
        <span>SCROLL</span>
      </motion.div>

      <motion.div
        className="suhana-tool-strip"
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.75, delay: 0.82, ease: [0.16, 1, 0.3, 1] }}
      >
        {tools.map(([label, Icon]) => (
          <a href="/tools" key={label}>
            <Icon size={18} />
            <span>{label}</span>
          </a>
        ))}
      </motion.div>
    </section>
  );
}

const rootEl = document.getElementById('suhana-react-hero-root');
if (rootEl) {
  createRoot(rootEl).render(<SuhanaHero />);
}

function initToolsWebgl() {
  const mount = document.getElementById('suhana-tools-webgl');
  if (!mount || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  document.body.classList.add('tools-immersive');
  gsap.utils.toArray('.tools-title, .tools-sub, .tools-lab-panel, .flagship-card, .tool-controls, .tool-box').forEach((item, index) => {
    gsap.fromTo(item, {
      y: 88,
      opacity: 0,
      filter: 'blur(16px)'
    }, {
      y: 0,
      opacity: 1,
      filter: 'blur(0px)',
      duration: 0.9,
      delay: (index % 4) * 0.035,
      ease: 'expo.out',
      scrollTrigger: {
        trigger: item,
        start: 'top 92%',
        end: 'top 58%',
        scrub: 0.35
      }
    });
  });

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
  camera.position.set(0, 0, 8);
  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.6));
  renderer.setClearColor(0x000000, 0);
  mount.appendChild(renderer.domElement);

  const rig = new THREE.Group();
  scene.add(rig);
  const cards = [...document.querySelectorAll('.tool-box')];
  const activeTarget = { x: 0, y: 0 };

  const texture = makeNebulaTexture();
  const pointGeo = new THREE.BufferGeometry();
  const amount = 760;
  const pos = new Float32Array(amount * 3);
  const color = new Float32Array(amount * 3);
  const palette = [new THREE.Color(0x7dd3fc), new THREE.Color(0x34d399), new THREE.Color(0xc4b5fd)];
  for (let i = 0; i < amount; i += 1) {
    const ring = 2.4 + Math.random() * 4.8;
    const angle = Math.random() * Math.PI * 2;
    pos[i * 3] = Math.cos(angle) * ring;
    pos[i * 3 + 1] = (Math.random() - 0.5) * 3.5;
    pos[i * 3 + 2] = Math.sin(angle) * ring;
    const picked = palette[i % palette.length];
    color[i * 3] = picked.r;
    color[i * 3 + 1] = picked.g;
    color[i * 3 + 2] = picked.b;
  }
  pointGeo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  pointGeo.setAttribute('color', new THREE.BufferAttribute(color, 3));
  const field = new THREE.Points(pointGeo, new THREE.PointsMaterial({
    size: 0.055,
    map: texture,
    vertexColors: true,
    transparent: true,
    opacity: 0.7,
    depthWrite: false,
    blending: THREE.AdditiveBlending
  }));
  rig.add(field);

  const portals = ['learn', 'create', 'utility', 'play'].map((cat, index) => {
    const mesh = new THREE.Mesh(
      new THREE.TorusKnotGeometry(0.42, 0.012, 120, 8, 2 + index, 3),
      new THREE.MeshBasicMaterial({ color: palette[index % palette.length], transparent: true, opacity: 0.62 })
    );
    mesh.position.set((index - 1.5) * 1.45, Math.sin(index) * 0.44, 0.25);
    mesh.userData.cat = cat;
    rig.add(mesh);
    return mesh;
  });

  gsap.fromTo(rig.position, { y: -0.45 }, { y: 0, duration: 1.2, ease: 'expo.out' });
  gsap.fromTo(renderer.domElement, { opacity: 0 }, { opacity: 1, duration: 0.8, ease: 'power2.out' });

  cards.forEach((card, index) => {
    card.addEventListener('pointerenter', () => {
      activeTarget.x = ((index % 3) - 1) * 0.28;
      activeTarget.y = ((Math.floor(index / 3) % 3) - 1) * -0.18;
      portals.forEach((portal) => {
        gsap.to(portal.scale, {
          x: portal.userData.cat === card.dataset.cat ? 1.55 : 0.86,
          y: portal.userData.cat === card.dataset.cat ? 1.55 : 0.86,
          z: portal.userData.cat === card.dataset.cat ? 1.55 : 0.86,
          duration: 0.42,
          ease: 'back.out(1.7)'
        });
      });
    });
  });

  const resize = () => {
    const rect = mount.getBoundingClientRect();
    renderer.setSize(Math.max(1, rect.width), Math.max(1, rect.height), false);
    camera.aspect = Math.max(1, rect.width) / Math.max(1, rect.height);
    camera.updateProjectionMatrix();
  };
  resize();
  window.addEventListener('resize', resize, { passive: true });

  let frameId = 0;
  const render = (timeMs) => {
    const time = timeMs * 0.001;
    rig.rotation.y += (activeTarget.x - rig.rotation.y) * 0.03;
    rig.rotation.x += (activeTarget.y - rig.rotation.x) * 0.03;
    field.rotation.y = time * 0.035;
    field.rotation.x = Math.sin(time * 0.34) * 0.09;
    portals.forEach((portal, index) => {
      portal.rotation.x = time * (0.32 + index * 0.07);
      portal.rotation.y = -time * (0.2 + index * 0.05);
    });
    renderer.render(scene, camera);
    frameId = requestAnimationFrame(render);
  };
  frameId = requestAnimationFrame(render);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initToolsWebgl, { once: true });
} else {
  initToolsWebgl();
}
