# Rotation Matrices

A rotation matrix is a 3×3 matrix that transforms vectors from one coordinate frame to another. Also known as Direction Cosine Matrices (DCM).

## Mathematical Representation

A rotation matrix is represented as:

$$
R = \begin{bmatrix}
r_{11} & r_{12} & r_{13} \\
r_{21} & r_{22} & r_{23} \\
r_{31} & r_{32} & r_{33}
\end{bmatrix}
$$

A rotation matrix $R$ satisfies the properties:

$$R^T R = I$$

$$\det(R) = 1$$

where $I$ is the identity matrix.

## Initialization

Rotation matrices can be created directly from elements, elementary rotations, or converted from other attitude representations:


```python
import brahe as bh
import numpy as np
import math

# Initialize from 9 individual elements (row-major order)
# Identity rotation
rm_identity = bh.RotationMatrix(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
print("Identity rotation matrix:")
print(f"  [{rm_identity.r11:.3f}, {rm_identity.r12:.3f}, {rm_identity.r13:.3f}]")
print(f"  [{rm_identity.r21:.3f}, {rm_identity.r22:.3f}, {rm_identity.r23:.3f}]")
print(f"  [{rm_identity.r31:.3f}, {rm_identity.r32:.3f}, {rm_identity.r33:.3f}]")

# Initialize from a matrix of elements
matrix_elements = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
rm_from_matrix = bh.RotationMatrix.from_matrix(matrix_elements)
print("\nFrom matrix of elements:")
print(
    f"  [{rm_from_matrix.r11:.3f}, {rm_from_matrix.r12:.3f}, {rm_from_matrix.r13:.3f}]"
)
print(
    f"  [{rm_from_matrix.r21:.3f}, {rm_from_matrix.r22:.3f}, {rm_from_matrix.r23:.3f}]"
)
print(
    f"  [{rm_from_matrix.r31:.3f}, {rm_from_matrix.r32:.3f}, {rm_from_matrix.r33:.3f}]"
)

# Common rotation: 90° about X-axis
angle_x = 30
rm_x = bh.RotationMatrix.Rx(angle_x, bh.AngleFormat.DEGREES)
print(f"\n{angle_x}° rotation about X-axis:")
print(f"  [{rm_x.r11:.3f}, {rm_x.r12:.3f}, {rm_x.r13:.3f}]")
print(f"  [{rm_x.r21:.3f}, {rm_x.r22:.3f}, {rm_x.r23:.3f}]")
print(f"  [{rm_x.r31:.3f}, {rm_x.r32:.3f}, {rm_x.r33:.3f}]")

# Common rotation: 90° about Y-axis
angle_y = 60
rm_y = bh.RotationMatrix.Ry(angle_y, bh.AngleFormat.DEGREES)
print(f"\n{angle_y}° rotation about Y-axis:")
print(f"  [{rm_y.r11:.3f}, {rm_y.r12:.3f}, {rm_y.r13:.3f}]")
print(f"  [{rm_y.r21:.3f}, {rm_y.r22:.3f}, {rm_y.r23:.3f}]")
print(f"  [{rm_y.r31:.3f}, {rm_y.r32:.3f}, {rm_y.r33:.3f}]")

# Common rotation: 90° about Z-axis
angle_z = 45
rm_z = bh.RotationMatrix.Rz(angle_z, bh.AngleFormat.DEGREES)
print(f"\n{angle_z}° rotation about Z-axis:")
print(f"  [{rm_z.r11:.3f}, {rm_z.r12:.3f}, {rm_z.r13:.3f}]")
print(f"  [{rm_z.r21:.3f}, {rm_z.r22:.3f}, {rm_z.r23:.3f}]")
print(f"  [{rm_z.r31:.3f}, {rm_z.r32:.3f}, {rm_z.r33:.3f}]")

# Initialize from another representation (quaternion)
q = bh.Quaternion(
    math.cos(math.radians(angle_z) / 2), 0, 0, math.sin(math.radians(angle_z) / 2)
)  # 90° about Z-axis
rm_from_q = bh.RotationMatrix.from_quaternion(q)
print(f"\nFrom quaternion ({angle_z}° about Z-axis):")
print(f"  [{rm_from_q.r11:.3f}, {rm_from_q.r12:.3f}, {rm_from_q.r13:.3f}]")
print(f"  [{rm_from_q.r21:.3f}, {rm_from_q.r22:.3f}, {rm_from_q.r23:.3f}]")
print(f"  [{rm_from_q.r31:.3f}, {rm_from_q.r32:.3f}, {rm_from_q.r33:.3f}]")

# Initialize from Euler angles (ZYX sequence)
euler_angles = bh.EulerAngle(
    bh.EulerAngleOrder.ZYX, angle_z, 0, 0, bh.AngleFormat.DEGREES
)
rm_from_euler = bh.RotationMatrix.from_euler_angle(euler_angles)
print(f"\nFrom Euler angles ({angle_z}° about Z-axis):")
print(f"  [{rm_from_euler.r11:.3f}, {rm_from_euler.r12:.3f}, {rm_from_euler.r13:.3f}]")
print(f"  [{rm_from_euler.r21:.3f}, {rm_from_euler.r22:.3f}, {rm_from_euler.r23:.3f}]")
print(f"  [{rm_from_euler.r31:.3f}, {rm_from_euler.r32:.3f}, {rm_from_euler.r33:.3f}]")

# Initialize from Euler axis and angle
axis = np.array([0, 0, 1])  # Z-axis
euler_axis = bh.EulerAxis(axis, angle_z, bh.AngleFormat.DEGREES)
rm_from_axis_angle = bh.RotationMatrix.from_euler_axis(euler_axis)
print(f"\nFrom Euler axis ({angle_z}° about Z-axis):")
print(
    f"  [{rm_from_axis_angle.r11:.3f}, {rm_from_axis_angle.r12:.3f}, {rm_from_axis_angle.r13:.3f}]"
)
print(
    f"  [{rm_from_axis_angle.r21:.3f}, {rm_from_axis_angle.r22:.3f}, {rm_from_axis_angle.r23:.3f}]"
)
print(
    f"  [{rm_from_axis_angle.r31:.3f}, {rm_from_axis_angle.r32:.3f}, {rm_from_axis_angle.r33:.3f}]"
)
```

**tip**
Brahe provides convenient methods to create rotation matrices for elementary rotations about the X, Y, and Z axes:

- `RotationMatrix.Rx(angle, format)`
- `RotationMatrix.Ry(angle, format)`
- `RotationMatrix.Rz(angle, format)`

## Output and Access

Access rotation matrix elements and convert to other formats:


```python
import brahe as bh

# Create a rotation matrix (45° about Z-axis)
rm = bh.RotationMatrix.Rz(45, bh.AngleFormat.DEGREES)

# Access individual elements
print("Individual elements (row-by-row):")
print(f"  r11: {rm.r11:.6f}, r12: {rm.r12:.6f}, r13: {rm.r13:.6f}")
print(f"  r21: {rm.r21:.6f}, r22: {rm.r22:.6f}, r23: {rm.r23:.6f}")
print(f"  r31: {rm.r31:.6f}, r32: {rm.r32:.6f}, r33: {rm.r33:.6f}")
# String representation
print("\nString representation:")
print(f"  {rm}")
```

## Operations

Rotation matrices support composition through matrix multiplication and vector rotation:


```python
import brahe as bh
import numpy as np

# Create two rotation matrices
# 90° rotation about X-axis
rm_x = bh.RotationMatrix(1.0, 0.0, 0.0, 0.0, 0.0, -1.0, 0.0, 1.0, 0.0)

# 90° rotation about Z-axis
rm_z = bh.RotationMatrix(0.0, -1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)

print("Rotation matrix X (90° about X):")
print(f"  [{rm_x.r11:.3f}, {rm_x.r12:.3f}, {rm_x.r13:.3f}]")
print(f"  [{rm_x.r21:.3f}, {rm_x.r22:.3f}, {rm_x.r23:.3f}]")
print(f"  [{rm_x.r31:.3f}, {rm_x.r32:.3f}, {rm_x.r33:.3f}]")

print("\nRotation matrix Z (90° about Z):")
print(f"  [{rm_z.r11:.3f}, {rm_z.r12:.3f}, {rm_z.r13:.3f}]")
print(f"  [{rm_z.r21:.3f}, {rm_z.r22:.3f}, {rm_z.r23:.3f}]")
print(f"  [{rm_z.r31:.3f}, {rm_z.r32:.3f}, {rm_z.r33:.3f}]")

# Matrix multiplication (compose rotations)
# Apply rm_x first, then rm_z
rm_composed = rm_z * rm_x
print("\nComposed rotation (X then Z):")
print(f"  [{rm_composed.r11:.3f}, {rm_composed.r12:.3f}, {rm_composed.r13:.3f}]")
print(f"  [{rm_composed.r21:.3f}, {rm_composed.r22:.3f}, {rm_composed.r23:.3f}]")
print(f"  [{rm_composed.r31:.3f}, {rm_composed.r32:.3f}, {rm_composed.r33:.3f}]")

# Transform a vector using rotation matrix
# Rotate vector [1, 0, 0] by 90° about Z-axis using matrix multiplication
R_z = rm_z.to_matrix()  # Get 3x3 numpy array
vector = np.array([1.0, 0.0, 0.0])
rotated = R_z @ vector  # Matrix-vector multiplication
print("\nVector transformation:")
print(f"  Original: [{vector[0]:.3f}, {vector[1]:.3f}, {vector[2]:.3f}]")
print(f"  Rotated:  [{rotated[0]:.3f}, {rotated[1]:.3f}, {rotated[2]:.3f}]")

# Transform another vector
vector2 = np.array([0.0, 1.0, 0.0])
rotated2 = R_z @ vector2
print(f"\n  Original: [{vector2[0]:.3f}, {vector2[1]:.3f}, {vector2[2]:.3f}]")
print(f"  Rotated:  [{rotated2[0]:.3f}, {rotated2[1]:.3f}, {rotated2[2]:.3f}]")

# Equality comparison
eq_result = rm_x == rm_z
neq_result = rm_x != rm_z
print("\nEquality comparison:")
print(f"  rm_x == rm_z: {eq_result}")
print(f"  rm_x != rm_z: {neq_result}")
```

## Conversions

Convert between rotation matrices and other attitude representations:


```python
import brahe as bh
import math

# Create a rotation matrix (45° about Z-axis)
rm = bh.RotationMatrix.Rz(45, bh.AngleFormat.DEGREES)

print("Original rotation matrix:")
print(f"  [{rm.r11:.6f}, {rm.r12:.6f}, {rm.r13:.6f}]")
print(f"  [{rm.r21:.6f}, {rm.r22:.6f}, {rm.r23:.6f}]")
print(f"  [{rm.r31:.6f}, {rm.r32:.6f}, {rm.r33:.6f}]")

# Convert to quaternion
q = rm.to_quaternion()
print("\nTo quaternion:")
print(f"  q = [{q.w:.6f}, {q.x:.6f}, {q.y:.6f}, {q.z:.6f}]")

# Convert to Euler angles (ZYX sequence)
ea_zyx = rm.to_euler_angle(bh.EulerAngleOrder.ZYX)
print("\nTo Euler angles (ZYX):")
print(f"  Yaw (Z):   {math.degrees(ea_zyx.phi):.3f}°")
print(f"  Pitch (Y): {math.degrees(ea_zyx.theta):.3f}°")
print(f"  Roll (X):  {math.degrees(ea_zyx.psi):.3f}°")

# Convert to Euler angles (XYZ sequence)
ea_xyz = rm.to_euler_angle(bh.EulerAngleOrder.XYZ)
print("\nTo Euler angles (XYZ):")
print(f"  Angle 1 (X): {math.degrees(ea_xyz.phi):.3f}°")
print(f"  Angle 2 (Y): {math.degrees(ea_xyz.theta):.3f}°")
print(f"  Angle 3 (Z): {math.degrees(ea_xyz.psi):.3f}°")

# Convert to Euler axis (axis-angle)
ea = rm.to_euler_axis()
print("\nTo Euler axis:")
print(f"  Axis: [{ea.axis[0]:.6f}, {ea.axis[1]:.6f}, {ea.axis[2]:.6f}]")
print(f"  Angle: {math.degrees(ea.angle):.3f}°")

# Round-trip conversion test
rm_roundtrip = bh.RotationMatrix.from_quaternion(q)
print("\nRound-trip (RotationMatrix → Quaternion → RotationMatrix):")
print(f"  [{rm_roundtrip.r11:.6f}, {rm_roundtrip.r12:.6f}, {rm_roundtrip.r13:.6f}]")
print(f"  [{rm_roundtrip.r21:.6f}, {rm_roundtrip.r22:.6f}, {rm_roundtrip.r23:.6f}]")
print(f"  [{rm_roundtrip.r31:.6f}, {rm_roundtrip.r32:.6f}, {rm_roundtrip.r33:.6f}]")
```

---

## See Also

- [Rotation Matrix API Reference](../../library_api/attitude/rotation_matrix.md)
- [Attitude Representations Overview](index.md)