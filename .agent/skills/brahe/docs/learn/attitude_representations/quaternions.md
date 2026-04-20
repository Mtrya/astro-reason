# Quaternions

A quaternion is a four-element mathematical object that can represent any 3D rotation without singularities. In Brahe, quaternions use the scalar-first convention: `[w, x, y, z]`.

## Mathematical Representation

A unit quaternion is defined as:

$$q = [w, x, y, z]$$

where $w^2 + x^2 + y^2 + z^2 = 1$ for unit quaternions. $w$ is the scalar part, and $(x, y, z)$ is the vector part. Quaternions can also be formulated with the scalar part as the last element, which brahe also supports for input/output.

## Initialization

Quaternions can be initialized in several ways, including directly from all other attitude representations:


```python
import math
import brahe as bh
import numpy as np


# Initialize from individual components (w, x, y, z)
# Always scalar-first in constructor
q1 = bh.Quaternion(0.924, 0.0, 0.0, 0.383)
print("From components (identity):")
print(f"  q = [{q1.w:.3f}, {q1.x:.3f}, {q1.y:.3f}, {q1.z:.3f}]")

# Initialize from vector/array [w, x, y, z]
# Can specify if scalar is first or last
q2 = bh.Quaternion.from_vector(np.array([0.924, 0.0, 0.0, 0.383]), scalar_first=True)
print("\nFrom vector:")
print(f"  q = [{q2.w:.3f}, {q2.x:.3f}, {q2.y:.3f}, {q2.z:.3f}]")

# Initialize from another representation (rotation matrix)
# 90° rotation about Z-axis
rm = bh.RotationMatrix.Rz(45, bh.AngleFormat.DEGREES)
q3 = bh.Quaternion.from_rotation_matrix(rm)
print("\nFrom rotation matrix (45° about Z-axis):")
print(f"  q = [{q3.w:.3f}, {q3.x:.3f}, {q3.y:.3f}, {q3.z:.3f}]")

# Initialize from Euler angles (ZYX sequence)
ea = bh.EulerAngle(
    bh.EulerAngleOrder.ZYX, math.pi / 4, 0.0, 0.0, bh.AngleFormat.RADIANS
)
q4 = bh.Quaternion.from_euler_angle(ea)
print("\nFrom Euler angles (45° yaw, ZYX):")
print(f"  q = [{q4.w:.3f}, {q4.x:.3f}, {q4.y:.3f}, {q4.z:.3f}]")

# Initialize from Euler axis (axis-angle representation)
axis = np.array([0.0, 0.0, 1.0])  # Z-axis
angle = math.pi / 4  # 45°
ea_rep = bh.EulerAxis(axis, angle, bh.AngleFormat.RADIANS)
q5 = bh.Quaternion.from_euler_axis(ea_rep)
print("\nFrom Euler axis (45° about Z-axis):")
print(f"  q = [{q5.w:.3f}, {q5.x:.3f}, {q5.y:.3f}, {q5.z:.3f}]")
```

## Output and Access

You can access quaternion components directly or convert them to other data formats:



```python
import brahe as bh

# Create a quaternion (45° rotation about Z-axis)
q = bh.Quaternion.from_rotation_matrix(bh.RotationMatrix.Rz(45, bh.AngleFormat.DEGREES))

# Access individual components
print("Individual components:")
print(f"  w (scalar): {q.w:.6f}")
print(f"  x: {q.x:.6f}")
print(f"  y: {q.y:.6f}")
print(f"  z: {q.z:.6f}")

# Directly access as a vector/array
vec = q.data
print("\nAs vector [w, x, y, z]:")
print(f"  {vec}: {type(vec)}")

# Or return copy as a NumPy array
vec_np = q.to_vector(scalar_first=True)
print("\nAs vector [w, x, y, z]:")
print(f"  {vec_np}: {type(vec_np)}")

# Return in different order (scalar last)
vec_np_last = q.to_vector(scalar_first=False)
print("\nAs scalar-last [x, y, z, w]:")
print(f"  {vec_np_last}: {type(vec_np_last)}")

# Display as string
print("\nString representation:")
print(f"  {q}")

print("\Repr representation:")
print(f"  {repr(q)}")
```

## Operations

Quaternions support multiplication, normalization, conjugation, inversion, and interpolation (through [Spherical Linear Interpolation (SLERP)](https://en.wikipedia.org/wiki/Slerp)):


```python
import brahe as bh
import math

# Create a quaternion from rotation matrix (90° about X, then 45° about Z)
q = bh.Quaternion.from_rotation_matrix(
    bh.RotationMatrix.Rx(90, bh.AngleFormat.DEGREES)
    * bh.RotationMatrix.Rz(45, bh.AngleFormat.DEGREES)
)

print("Original quaternion:")
print(f"  q = [{q.w:.6f}, {q.x:.6f}, {q.y:.6f}, {q.z:.6f}]")

# Compute norm
norm = q.norm()
print(f"\nNorm: {norm:.6f}")

# Normalize quaternion (in-place)
q.normalize()  # In-place normalization (This shouldn't really do anything here since q already applies normalization on creation)
print("After normalization:")
print(f"  q = [{q.w:.6f}, {q.x:.6f}, {q.y:.6f}, {q.z:.6f}]")
print(f"  Norm: {q.norm():.6f}")

# Compute conjugate
q_conj = q.conjugate()
print("\nConjugate:")
print(f"  q* = [{q_conj.w:.6f}, {q_conj.x:.6f}, {q_conj.y:.6f}, {q_conj.z:.6f}]")

# Compute inverse (same as conjugate for normalized quaternions)
q_inv = q.inverse()
print("\nInverse:")
print(f"  q^-1 = [{q_inv.w:.6f}, {q_inv.x:.6f}, {q_inv.y:.6f}, {q_inv.z:.6f}]")

# Quaternion multiplication (compose rotations)
# 90° about X, then 90° about Z
q_x = bh.Quaternion(math.cos(math.pi / 4), math.sin(math.pi / 4), 0.0, 0.0)
q_z = bh.Quaternion(math.cos(math.pi / 4), 0.0, 0.0, math.sin(math.pi / 4))
q_composed = q_z * q_x  # Apply q_x first, then q_z
print("\nComposed rotation (90° X then 90° Z):")
print(f"  q_x = [{q_x.w:.6f}, {q_x.x:.6f}, {q_x.y:.6f}, {q_x.z:.6f}]")
print(f"  q_z = [{q_z.w:.6f}, {q_z.x:.6f}, {q_z.y:.6f}, {q_z.z:.6f}]")
print(
    f"  q_composed = [{q_composed.w:.6f}, {q_composed.x:.6f}, {q_composed.y:.6f}, {q_composed.z:.6f}]"
)

# Multiply q and its inverse to verify identity
identity = q * q_inv
print("\nq * q^-1 (should be identity):")
print(
    f"  q_identity = [{identity.w:.6f}, {identity.x:.6f}, {identity.y:.6f}, {identity.z:.6f}]"
)

# SLERP (Spherical Linear Interpolation) between two quaternions
# Interpolate from q_x (90° about X) to q_z (90° about Z)
print("\nSLERP interpolation from q_x to q_z:")
q_slerp_0 = q_x.slerp(q_z, 0.0)  # t=0, should equal q_x
print(
    f"  t=0.0: [{q_slerp_0.w:.6f}, {q_slerp_0.x:.6f}, {q_slerp_0.y:.6f}, {q_slerp_0.z:.6f}]"
)
q_slerp_25 = q_x.slerp(q_z, 0.25)
print(
    f"  t=0.25: [{q_slerp_25.w:.6f}, {q_slerp_25.x:.6f}, {q_slerp_25.y:.6f}, {q_slerp_25.z:.6f}]"
)
q_slerp_5 = q_x.slerp(q_z, 0.5)  # t=0.5, halfway
print(
    f"  t=0.5: [{q_slerp_5.w:.6f}, {q_slerp_5.x:.6f}, {q_slerp_5.y:.6f}, {q_slerp_5.z:.6f}]"
)
q_slerp_75 = q_x.slerp(q_z, 0.75)
print(
    f"  t=0.75: [{q_slerp_75.w:.6f}, {q_slerp_75.x:.6f}, {q_slerp_75.y:.6f}, {q_slerp_75.z:.6f}]"
)
q_slerp_1 = q_x.slerp(q_z, 1.0)  # t=1, should equal q_z
print(
    f"  t=1.0: [{q_slerp_1.w:.6f}, {q_slerp_1.x:.6f}, {q_slerp_1.y:.6f}, {q_slerp_1.z:.6f}]"
)
```

## Conversions

You can convert quaternions to all other attitude representations and vice versa:


```python
import brahe as bh
import math

# Create a quaternion (45° rotation about Z-axis)
q = bh.Quaternion.from_rotation_matrix(bh.RotationMatrix.Rz(45, bh.AngleFormat.DEGREES))

print("Original quaternion:")
print(f"  q = [{q.w:.6f}, {q.x:.6f}, {q.y:.6f}, {q.z:.6f}]")

# Convert to rotation matrix
rm = q.to_rotation_matrix()
print("\nTo rotation matrix:")
print(f"  [{rm.r11:.6f}, {rm.r12:.6f}, {rm.r13:.6f}]")
print(f"  [{rm.r21:.6f}, {rm.r22:.6f}, {rm.r23:.6f}]")
print(f"  [{rm.r31:.6f}, {rm.r32:.6f}, {rm.r33:.6f}]")

# Convert to Euler angles (ZYX sequence)
ea_zyx = q.to_euler_angle(bh.EulerAngleOrder.ZYX)
print("\nTo Euler angles (ZYX):")
print(f"  Yaw (Z):   {math.degrees(ea_zyx.phi):.3f}°")
print(f"  Pitch (Y): {math.degrees(ea_zyx.theta):.3f}°")
print(f"  Roll (X):  {math.degrees(ea_zyx.psi):.3f}°")

# Convert to Euler angles (XYZ sequence)
ea_xyz = q.to_euler_angle(bh.EulerAngleOrder.XYZ)
print("\nTo Euler angles (XYZ):")
print(f"  Angle 1 (X): {math.degrees(ea_xyz.phi):.3f}°")
print(f"  Angle 2 (Y): {math.degrees(ea_xyz.theta):.3f}°")
print(f"  Angle 3 (Z): {math.degrees(ea_xyz.psi):.3f}°")

# Convert to Euler axis (axis-angle)
ea = q.to_euler_axis()
print("\nTo Euler axis:")
print(f"  Axis: [{ea.axis[0]:.6f}, {ea.axis[1]:.6f}, {ea.axis[2]:.6f}]")
print(f"  Angle: {math.degrees(ea.angle):.3f}°")

# Round-trip conversion test
q_roundtrip = bh.Quaternion.from_rotation_matrix(rm)
print("\nRound-trip (Quaternion → RotationMatrix → Quaternion):")
print(
    f"  q_rt = [{q_roundtrip.w:.6f}, {q_roundtrip.x:.6f}, {q_roundtrip.y:.6f}, {q_roundtrip.z:.6f}]"
)
```

---

## See Also

- [Quaternion API Reference](../../library_api/attitude/quaternion.md)
- [Attitude Representations Overview](index.md)