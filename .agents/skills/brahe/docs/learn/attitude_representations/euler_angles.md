# Euler Angles

Euler angles represent rotations as three sequential rotations about coordinate axes.

## Overview

Euler angles describe orientation using three angles representing sequential rotations about specified axes. Brahe supports all 12 possible Euler angle sequences (e.g., XYZ, ZYX, ZYZ).

## Mathematical Representation

An Euler angle rotation is specified by:

- Three angles: $(\phi, \theta, \psi)$
- A rotation sequence (e.g., XYZ, ZYX)

## Sequences

Brahe supports all valid Euler angle sequences, though some are more commonly used are:

- **ZYX (3-2-1)**: Common in aerospace applications. Known as yaw-pitch-roll.
- **XYZ (1-2-3)**: Common in robotics
- **ZYZ (3-1-3)**: Common in classical mechanics

## Initialization

Euler angles can be created from individual angles with a specified rotation sequence, or converted from other attitude representations. When creating a new `EulerAngle` object, the rotation sequence of the created object must be specified.


```python
import brahe as bh
import numpy as np
import math

# Initialize from individual angles with ZYX sequence (yaw-pitch-roll)
# 45° yaw, 30° pitch, 15° roll
ea_zyx = bh.EulerAngle(
    bh.EulerAngleOrder.ZYX,
    45.0,  # Yaw (Z)
    30.0,  # Pitch (Y)
    15.0,  # Roll (X)
    bh.AngleFormat.DEGREES,
)
print("ZYX Euler angles (yaw-pitch-roll):")
print(f"  Yaw (Z):   {math.degrees(ea_zyx.phi):.1f}°")
print(f"  Pitch (Y): {math.degrees(ea_zyx.theta):.1f}°")
print(f"  Roll (X):  {math.degrees(ea_zyx.psi):.1f}°")
print(f"  Order: {ea_zyx.order}")

# Initialize from vector with XYZ sequence
angles_vec = np.array([15.0, 30.0, 45.0])
ea_xyz = bh.EulerAngle.from_vector(
    angles_vec, bh.EulerAngleOrder.XYZ, bh.AngleFormat.DEGREES
)
print("\nXYZ Euler angles (from vector):")
print(f"  Angle 1 (X): {math.degrees(ea_xyz.phi):.1f}°")
print(f"  Angle 2 (Y): {math.degrees(ea_xyz.theta):.1f}°")
print(f"  Angle 3 (Z): {math.degrees(ea_xyz.psi):.1f}°")
print(f"  Order: {ea_xyz.order}")

# Simple rotation about single axis (45° about Z using ZYX)
ea_z_only = bh.EulerAngle(
    bh.EulerAngleOrder.ZYX,
    45.0,  # Z
    0.0,  # Y
    0.0,  # X
    bh.AngleFormat.DEGREES,
)
print("\nSingle-axis rotation (45° about Z using ZYX):")
print(f"  Yaw (Z):   {math.degrees(ea_z_only.phi):.1f}°")
print(f"  Pitch (Y): {math.degrees(ea_z_only.theta):.1f}°")
print(f"  Roll (X):  {math.degrees(ea_z_only.psi):.1f}°")

# Initialize from another representation (quaternion)
q = bh.Quaternion(math.cos(math.pi / 8), 0.0, 0.0, math.sin(math.pi / 8))
ea_from_q = bh.EulerAngle.from_quaternion(q, bh.EulerAngleOrder.ZYX)
print("\nFrom quaternion (45° about Z):")
print(f"  Yaw (Z):   {math.degrees(ea_from_q.phi):.1f}°")
print(f"  Pitch (Y): {math.degrees(ea_from_q.theta):.1f}°")
print(f"  Roll (X):  {math.degrees(ea_from_q.psi):.1f}°")

# Initialize from Rotation Matrix
rm = bh.RotationMatrix.Rz(45.0, bh.AngleFormat.DEGREES)
ea_from_rm = bh.EulerAngle.from_rotation_matrix(rm, bh.EulerAngleOrder.ZYX)
print("\nFrom rotation matrix (45° about Z):")
print(f"  Yaw (Z):   {math.degrees(ea_from_rm.phi):.1f}°")
print(f"  Pitch (Y): {math.degrees(ea_from_rm.theta):.1f}°")
print(f"  Roll (X):  {math.degrees(ea_from_rm.psi):.1f}°")

# Initialize from Euler Axis
euler_axis = bh.EulerAxis(np.array([0.0, 0.0, 1.0]), 45.0, bh.AngleFormat.DEGREES)
ea_from_ea = bh.EulerAngle.from_euler_axis(euler_axis, bh.EulerAngleOrder.ZYX)

print("\nFrom Euler axis (45° about Z):")
print(f"  Yaw (Z):   {math.degrees(ea_from_ea.phi):.1f}°")
print(f"  Pitch (Y): {math.degrees(ea_from_ea.theta):.1f}°")
print(f"  Roll (X):  {math.degrees(ea_from_ea.psi):.1f}°")

# Initialize from one EulerAngle to another with different order
# Start with XZY order
ea_xzy = bh.EulerAngle.from_euler_angle(ea_zyx, bh.EulerAngleOrder.XZY)
print("\nXZY Euler angles from ZYX:")
print(f"  Angle 1 (X): {math.degrees(ea_xzy.phi):.1f}°")
print(f"  Angle 2 (Z): {math.degrees(ea_xzy.theta):.1f}°")
print(f"  Angle 3 (Y): {math.degrees(ea_xzy.psi):.1f}°")
print(f"  Order: {ea_xzy.order}")

# Convert to ZYX order (same physical rotation, different representation)
# Go through quaternion as intermediate representation
q_xzy = ea_xzy.to_quaternion()
ea_zyx_converted = bh.EulerAngle.from_quaternion(q_xzy, bh.EulerAngleOrder.ZYX)
print("\nConverted back to ZYX order (same rotation):")
print(f"  Angle 1 (Z): {math.degrees(ea_zyx_converted.phi):.1f}°")
print(f"  Angle 2 (Y): {math.degrees(ea_zyx_converted.theta):.1f}°")
print(f"  Angle 3 (X): {math.degrees(ea_zyx_converted.psi):.1f}°")
print(f"  Order: {ea_zyx_converted.order}")
```

## Conversions

Convert between Euler angles and other attitude representations:


```python
import brahe as bh
import math

# Create Euler angles (ZYX: 45° yaw, 30° pitch, 15° roll)
ea = bh.EulerAngle(
    bh.EulerAngleOrder.ZYX,
    math.radians(45.0),
    math.radians(30.0),
    math.radians(15.0),
    bh.AngleFormat.RADIANS,
)

print("Original Euler angles (ZYX):")
print(f"  Yaw (Z):   {math.degrees(ea.phi):.1f}°")
print(f"  Pitch (Y): {math.degrees(ea.theta):.1f}°")
print(f"  Roll (X):  {math.degrees(ea.psi):.1f}°")

# Convert to quaternion
q = ea.to_quaternion()
print("\nTo quaternion:")
print(f"  q = [{q.w:.6f}, {q.x:.6f}, {q.y:.6f}, {q.z:.6f}]")

# Convert to rotation matrix
rm = ea.to_rotation_matrix()
print("\nTo rotation matrix:")
print(f"  [{rm.r11:.6f}, {rm.r12:.6f}, {rm.r13:.6f}]")
print(f"  [{rm.r21:.6f}, {rm.r22:.6f}, {rm.r23:.6f}]")
print(f"  [{rm.r31:.6f}, {rm.r32:.6f}, {rm.r33:.6f}]")

# Convert to Euler axis (axis-angle)
ea_axis = ea.to_euler_axis()
print("\nTo Euler axis:")
print(f"  Axis: [{ea_axis.axis[0]:.6f}, {ea_axis.axis[1]:.6f}, {ea_axis.axis[2]:.6f}]")
print(f"  Angle: {math.degrees(ea_axis.angle):.3f}°")
```

---

## See Also

- [Euler Angles API Reference](../../library_api/attitude/euler_angles.md)
- [Attitude Representations Overview](index.md)