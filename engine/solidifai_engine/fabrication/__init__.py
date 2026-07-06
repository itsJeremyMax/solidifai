"""Fabrication subsystem — provider abstraction + per-provider implementations.

Sub-modules:
  base      — FabricationProvider protocol + shared dataclasses (pure, no OCC)
  estimate  — geometric fallback estimate (pure math, no slicer required)
  orca      — OrcaProvider: detect, profiles, headless slice quote, app handoff
"""
