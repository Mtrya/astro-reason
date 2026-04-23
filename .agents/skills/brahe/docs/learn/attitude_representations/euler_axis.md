# Euler Axis (Axis-Angle)

The Euler axis representation describes rotations using a rotation axis and angle.

## Overview

Also known as axis-angle representation, this describes any rotation as a single rotation about a unit vector (axis) by a specified angle.

## Mathematical Representation

An Euler axis rotation is specified by:

- Unit vector (axis): $\hat{n} = [n_x, n_y, n_z]$ where $|\hat{n}| = 1$
- Rotation angle: $\theta$ (in radians)

Together: $[\theta, n_x, n_y, n_z]$ (4 parameters)

## Initialization

Euler axis representations can be created from an axis vector and angle, or converted from other attitude representations:


```python
import brahe as bh
import numpy as np
import math

# Initialize from axis vector and angle
# 45° rotation about Z-axis
axis_z = np.array([0.0, 0.0, 1.0])
angle = math.radians(45.0)
ea_z = bh.EulerAxis(axis_z, angle, bh.AngleFormat.RADIANS)

print("45° rotation about Z-axis:")
print(f"  Axis: [{ea_z.axis[0]:.3f}, {ea_z.axis[1]:.3f}, {ea_z.axis[2]:.3f}]")
print(f"  Angle: {math.degrees(ea_z.angle):.1f}°")

# 90° rotation about X-axis
axis_x = np.array([1.0, 0.0, 0.0])
ea_x = bh.EulerAxis(axis_x, math.radians(90.0), bh.AngleFormat.RADIANS)

print("\n90° rotation about X-axis:")
print(f"  Axis: [{ea_x.axis[0]:.3f}, {ea_x.axis[1]:.3f}, {ea_x.axis[2]:.3f}]")
print(f"  Angle: {math.degrees(ea_x.angle):.1f}°")

# Initialize from another representation (quaternion)
q = bh.Quaternion(math.cos(math.pi / 8), 0.0, 0.0, math.sin(math.pi / 8))
ea_from_q = bh.EulerAxis.from_quaternion(q)

print("\nFrom quaternion (45° about Z):")
print(
    f"  Axis: [{ea_from_q.axis[0]:.6f}, {ea_from_q.axis[1]:.6f}, {ea_from_q.axis[2]:.6f}]"
)
print(f"  Angle: {math.degrees(ea_from_q.angle):.1f}°")

# Initialize from rotation matrix
rm = bh.RotationMatrix.Rz(45, bh.AngleFormat.DEGREES)
ea_from_rm = bh.EulerAxis.from_rotation_matrix(rm)

print("\nFrom rotation matrix (45° about Z):")
print(
    f"  Axis: [{ea_from_rm.axis[0]:.6f}, {ea_from_rm.axis[1]:.6f}, {ea_from_rm.axis[2]:.6f}]"
)
print(f"  Angle: {math.degrees(ea_from_rm.angle):.1f}°")

# Initialize from EulerAngle
euler_angle = bh.EulerAngle(
    bh.EulerAngleOrder.ZYX, 45.0, 0.0, 0.0, bh.AngleFormat.DEGREES
)
ea_from_euler = bh.EulerAxis.from_euler_angle(euler_angle)

print("\nFrom EulerAngle (45° about Z):")
print(
    f"  Axis: [{ea_from_euler.axis[0]:.6f}, {ea_from_euler.axis[1]:.6f}, {ea_from_euler.axis[2]:.6f}]"
)
print(f"  Angle: {math.degrees(ea_from_euler.angle):.1f}°")
```

## Conversions

Convert between Euler axis and other attitude representations:


```python
import brahe as bh
import numpy as np
import math

# Create an Euler axis (45° rotation about Z-axis)
ea = bh.EulerAxis(np.array([0.0, 0.0, 1.0]), math.radians(45.0), bh.AngleFormat.RADIANS)

print("Original Euler axis:")
print(f"  Axis: [{ea.axis[0]:.6f}, {ea.axis[1]:.6f}, {ea.axis[2]:.6f}]")
print(f"  Angle: {math.degrees(ea.angle):.1f}°")

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

# Convert to Euler angles (ZYX sequence)
ea_angles_zyx = ea.to_euler_angle(bh.EulerAngleOrder.ZYX)
print("\nTo Euler angles (ZYX):")
print(f"  Yaw (Z):   {math.degrees(ea_angles_zyx.phi):.3f}°")
print(f"  Pitch (Y): {math.degrees(ea_angles_zyx.theta):.3f}°")
print(f"  Roll (X):  {math.degrees(ea_angles_zyx.psi):.3f}°")

# Convert to Euler angles (XYZ sequence)
ea_angles_xyz = ea.to_euler_angle(bh.EulerAngleOrder.XYZ)
print("\nTo Euler angles (XYZ):")
print(f"  Angle 1 (X): {math.degrees(ea_angles_xyz.phi):.3f}°")
print(f"  Angle 2 (Y): {math.degrees(ea_angles_xyz.theta):.3f}°")
print(f"  Angle 3 (Z): {math.degrees(ea_angles_xyz.psi):.3f}°")

# Round-trip conversion test
q_roundtrip = ea.to_quaternion()
ea_roundtrip = bh.EulerAxis.from_quaternion(q_roundtrip)
print("\nRound-trip (EulerAxis → Quaternion → EulerAxis):")
print(
    f"  Axis: [{ea_roundtrip.axis[0]:.6f}, {ea_roundtrip.axis[1]:.6f}, {ea_roundtrip.axis[2]:.6f}]"
)
print(f"  Angle: {math.degrees(ea_roundtrip.angle):.1f}°")
```

---

## See Also

- [Euler Axis API Reference](../../library_api/attitude/euler_axis.md)
- [Attitude Representations Overview](index.md)