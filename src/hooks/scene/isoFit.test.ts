import { describe, it, expect } from "vitest";
import * as THREE from "three";
import { fitDistance, placeIsoCamera } from "./isoFit";

describe("isoFit", () => {
  describe("fitDistance", () => {
    it("is strictly positive", () => {
      expect(fitDistance(1, 38)).toBeGreaterThan(0);
      expect(fitDistance(100, 38)).toBeGreaterThan(0);
    });

    it("is monotonic non-decreasing in maxDim (bigger box → farther)", () => {
      expect(fitDistance(2, 38)).toBeGreaterThanOrEqual(fitDistance(1, 38));
      expect(fitDistance(50, 38)).toBeGreaterThan(fitDistance(10, 38));
      // Linearity check: doubling the box doubles the distance.
      expect(fitDistance(20, 38)).toBeCloseTo(2 * fitDistance(10, 38));
    });

    it("uses the fov — a wider fov fits the same box from closer", () => {
      // tan grows with the angle, so the padded term shrinks as fov widens.
      expect(fitDistance(10, 60)).toBeLessThan(fitDistance(10, 38));
      expect(fitDistance(10, 90)).toBeLessThan(fitDistance(10, 60));
    });
  });

  describe("placeIsoCamera", () => {
    const center = new THREE.Vector3(0, 0, 0);
    const box = new THREE.Box3(
      new THREE.Vector3(-0.5, -0.5, -0.5),
      new THREE.Vector3(0.5, 0.5, 0.5),
    );

    it("seats the camera at fitDistance along the (1,1,1) iso direction", () => {
      const cam = new THREE.PerspectiveCamera(38, 1, 0.1, 1000);
      placeIsoCamera(cam, box);

      const expected = fitDistance(1, 38);
      expect(cam.position.distanceTo(center)).toBeCloseTo(expected);

      // Direction from center is the normalized iso corner.
      const dir = cam.position.clone().sub(center).normalize();
      const iso = new THREE.Vector3(1, 1, 1).normalize();
      expect(dir.x).toBeCloseTo(iso.x);
      expect(dir.y).toBeCloseTo(iso.y);
      expect(dir.z).toBeCloseTo(iso.z);
    });

    it("sets a sane depth range (0 < near < far)", () => {
      const cam = new THREE.PerspectiveCamera(38, 1, 0.1, 1000);
      placeIsoCamera(cam, box);
      expect(cam.near).toBeGreaterThan(0);
      expect(cam.near).toBeLessThan(cam.far);
    });
  });
});
