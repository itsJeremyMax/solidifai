import { describe, it, expect } from "vitest";
import * as THREE from "three";
import { captureExplodeBasis, applyExplode } from "./explode";

function partAt(x: number, y: number, z: number, size = 2): THREE.Object3D {
  const g = new THREE.Group();
  g.add(new THREE.Mesh(new THREE.BoxGeometry(size, size, size)));
  g.position.set(x, y, z);
  g.updateMatrixWorld(true);
  return g;
}

function minWorldY(parts: THREE.Object3D[], root: THREE.Object3D): number {
  root.updateMatrixWorld(true);
  return Math.min(...parts.map((p) => new THREE.Box3().setFromObject(p).min.y));
}

describe("explode (radial homothety, planted on the grid)", () => {
  it("leaves parts assembled at factor 0", () => {
    const parts = [partAt(-10, 0, 0), partAt(10, 5, 0)];
    const root = new THREE.Group();
    parts.forEach((p) => root.add(p));
    root.updateMatrixWorld(true);
    const basis = captureExplodeBasis(parts);
    applyExplode(parts, basis, 0);
    expect(parts[0].position.x).toBeCloseTo(-10);
    expect(parts[1].position.y).toBeCloseTo(5);
  });

  it("spreads parts outward in all directions (radial)", () => {
    const px = partAt(10, 0, 0);
    const nx = partAt(-10, 0, 0);
    const pz = partAt(0, 0, 10);
    const nz = partAt(0, 0, -10);
    const parts = [px, nx, pz, nz];
    const root = new THREE.Group();
    parts.forEach((p) => root.add(p));
    root.updateMatrixWorld(true);
    const basis = captureExplodeBasis(parts);
    applyExplode(parts, basis, 100);
    expect(px.position.x).toBeGreaterThan(10);
    expect(nx.position.x).toBeLessThan(-10);
    expect(pz.position.z).toBeGreaterThan(10);
    expect(nz.position.z).toBeLessThan(-10);
  });

  it("keeps everything on or above the grid, including downward parts", () => {
    const top = partAt(0, 10, 0);
    const bottom = partAt(0, -10, 0);
    const side = partAt(10, 0, 0);
    const parts = [top, bottom, side];
    const root = new THREE.Group();
    parts.forEach((p) => root.add(p));
    root.updateMatrixWorld(true);
    const basis = captureExplodeBasis(parts);
    const floorY = basis.floorY;
    for (const f of [25, 50, 75, 100]) {
      applyExplode(parts, basis, f);
      expect(minWorldY(parts, root)).toBeGreaterThanOrEqual(floorY - 1e-6);
    }
  });

  it("keeps a stacked base planted on the grid and lifts the part above it straight up", () => {
    const base = partAt(0, 0, 0);
    const lid = partAt(0, 10, 0);
    const parts = [base, lid];
    const root = new THREE.Group();
    parts.forEach((p) => root.add(p));
    root.updateMatrixWorld(true);
    const basis = captureExplodeBasis(parts);
    const floorY = basis.floorY;
    applyExplode(parts, basis, 100);
    expect(base.position.x).toBeCloseTo(0);
    expect(base.position.z).toBeCloseTo(0);
    root.updateMatrixWorld(true);
    expect(new THREE.Box3().setFromObject(base).min.y).toBeCloseTo(floorY);
    expect(lid.position.x).toBeCloseTo(0);
    expect(lid.position.z).toBeCloseTo(0);
    expect(lid.position.y).toBeGreaterThan(10);
  });

  it("leaves a part at the assembly center horizontally fixed", () => {
    const center = partAt(0, 0, 0);
    const a = partAt(20, 0, 0);
    const b = partAt(-20, 0, 0);
    const parts = [center, a, b];
    const root = new THREE.Group();
    parts.forEach((p) => root.add(p));
    root.updateMatrixWorld(true);
    const basis = captureExplodeBasis(parts);
    applyExplode(parts, basis, 100);
    expect(center.position.x).toBeCloseTo(0);
    expect(center.position.z).toBeCloseTo(0);
  });

  it("keeps an off-center base planted (no horizontal drift) while the top lifts", () => {
    // Small centered base on the grid; lid far offset in +X and elevated pulls
    // the union center sideways — which previously dragged the base horizontally.
    const base = partAt(0, 0, 0, 2);
    const lid = partAt(10, 5, 0, 2);
    const parts = [base, lid];
    const root = new THREE.Group();
    parts.forEach((p) => root.add(p));
    root.updateMatrixWorld(true);
    const basis = captureExplodeBasis(parts);
    const floorY = basis.floorY;
    applyExplode(parts, basis, 100);
    expect(base.position.x).toBeCloseTo(0);
    expect(base.position.z).toBeCloseTo(0);
    root.updateMatrixWorld(true);
    expect(new THREE.Box3().setFromObject(base).min.y).toBeCloseTo(floorY);
  });

  it("applies the spread under a scaled parent", () => {
    const a = partAt(-10, 0, 0);
    const b = partAt(10, 0, 0);
    const parts = [a, b];
    const root = new THREE.Group();
    root.scale.setScalar(2);
    parts.forEach((p) => root.add(p));
    root.updateMatrixWorld(true);
    const basis = captureExplodeBasis(parts);
    applyExplode(parts, basis, 100);
    expect(a.position.x).toBeLessThan(-10);
    expect(b.position.x).toBeCloseTo(-a.position.x);
  });
});
