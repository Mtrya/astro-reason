# True, Eccentric, and Mean Anomaly

This section deals with the conversion between true, eccentric, and mean 
anomaly. 

True anomaly, frequently denoted $\nu$, is the angular parameter that defines 
the position of an object moving along a Keplerian orbit. It is the angle 
between the eccentricity vector (vector pointing from the main pericenter to 
the periapsis) and the current position of the body in the orbital plane itself.

The eccentric anomaly, $E$, is another angular parameter that defines the position 
of an object moving along a Keplerian orbit if viewed from the center of the 
ellipse. 

Finally, the mean anomaly, $M$, defines the fraction of an orbital period that has 
elapsed since the orbiting object has passed its periapsis. It is the angle 
from the pericenter an object moving on a fictitious circular orbit with the 
same semi-major axis would have progressed through in the same time as the 
body on the true elliptical orbit.

Conversion between all types of angular anomaly is possible. However, there is 
no known direct conversion between true and mean anomaly. Conversion between the two is 
accomplished by transformation through eccentric anomaly.

## True and Eccentric Anomaly Conversions

To convert from true anomaly to eccentric anomaly, you can use the function 
`anomaly_eccentric_to_true`. To perform the reverse conversion use 
`anomaly_true_to_eccentric`.

Eccentric anomaly can be converted to true anomaly by using equations derived using equations 
from Vallado[^1]. Starting from Equation (2-12)
$$
\sin{\nu} = \frac{\sin{E}\sqrt{1-e^2}}{1 - e\cos{E}}
$$
can be divided by
$$
\cos{\nu} =  \frac{\cos{E}-e}{1 - e\cos{E}}
$$
and rearrange to get
$$
\nu = \arctan{\frac{\sin{E}\sqrt{1-e^2}}{\cos{E}-e}}
$$

This conversion is what is implemented by `anomaly_eccentric_to_true`. Similarly, we can derive
$$
E = \arctan{\frac{\sin{\nu}\sqrt{1-e^2}}{\cos{\nu}+e}}
$$
which allows for conversion from true anomaly to eccentric anomaly and is implemented in 
`anomaly_true_to_eccentric`.


```python
import brahe as bh

bh.initialize_eop()

nu = 45.0  # Starting true anomaly (degrees)
e = 0.01  # Eccentricity

# Convert to eccentric anomaly
ecc_anomaly = bh.anomaly_true_to_eccentric(nu, e, angle_format=bh.AngleFormat.DEGREES)
print(f"True anomaly:      {nu:.3f} deg")
print(f"Eccentric anomaly: {ecc_anomaly:.3f} deg")

# Convert back from eccentric to true anomaly
nu_2 = bh.anomaly_eccentric_to_true(ecc_anomaly, e, angle_format=bh.AngleFormat.DEGREES)
print(f"Round-trip result: {nu_2:.3f} deg")

# Verify round-trip accuracy
print(f"Difference:        {abs(nu - nu_2):.2e} deg")
```



**Plot Source**

```python
import os
import pathlib
import sys
import plotly.graph_objects as go
import brahe as bh

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from brahe_theme import get_theme_colors, save_themed_html

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))

# Ensure output directory exists
os.makedirs(OUTDIR, exist_ok=True)

# Generate data

# Generate range of true anomalies (degrees)
nu = [x for x in range(0, 360)]

# Compute eccentric anomaly for range of eccentricities
eccentricities = [0.0, 0.1, 0.3, 0.5, 0.7, 0.9]
ecc_data = {}
for e in eccentricities:
    # Take output mod 360 to wrap from 0 to 360 degrees
    ecc_data[e] = [
        bh.anomaly_true_to_eccentric(x, e, angle_format=bh.AngleFormat.DEGREES) % 360
        for x in nu
    ]

# Create figure with theme support


def create_figure(theme):
    """Create figure with theme-specific colors."""
    colors = get_theme_colors(theme)

    fig = go.Figure()

    # Color palette for different eccentricities
    color_palette = [
        colors["primary"],
        colors["secondary"],
        colors["accent"],
        colors["error"],
        colors["primary"],
        colors["secondary"],
    ]

    # Add traces for each eccentricity
    for i, e in enumerate(eccentricities):
        fig.add_trace(
            go.Scatter(
                x=nu,
                y=ecc_data[e],
                mode="lines",
                line=dict(color=color_palette[i % len(color_palette)], width=2),
                name=f"e = {e:.1f}",
                showlegend=True,
            )
        )

    # Configure axes
    fig.update_xaxes(
        tickmode="linear",
        tick0=0,
        dtick=30,
        title_text="True Anomaly (deg)",
        range=[0, 360],
        showgrid=False,
    )

    fig.update_yaxes(
        tickmode="linear",
        tick0=0,
        dtick=30,
        title_text="Eccentric Anomaly (deg)",
        range=[0, 360],
        showgrid=False,
    )

    return fig


# Generate and save both themed versions
light_path, dark_path = save_themed_html(create_figure, OUTDIR / SCRIPT_NAME)
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")
```

## Eccentric and Mean Anomaly Conversions

To convert from true anomaly to eccentric anomaly, you can use the function
`anomaly_eccentric_to_mean`. To perform the reverse conversion use
`anomaly_mean_to_eccentric`. 

Conversion from eccentric anomaly to mean anomaly is accomplished by application of Kepler's 
equation
$$
M = E - e\sin{E}
$$
which is implemented in `anomaly_eccentric_to_mean`.

Converting back from mean anomaly to eccentric anomaly is more challenging.
There is no known closed-form solution to convert from mean anomaly to eccentric anomaly. 
Instead, we introduce the auxiliary equation
$$
f(E) = E - e\sin(E) - M
$$
And treat the problem as numerically solving for the root of $f$ for a given $M$. This iteration 
can be accomplished using Newton's method. Starting from an initial guess $E_0$ the value of 
$E_*$ can be iteratively updated using
$$
E_{i+1} = \frac{f(E_i)}{f^\prime(E_i)}= E_i - \frac{E_i - e\sin{E_i} - M}{1 - e\cos{E_i}}
$$
This update is performed until a coverage value of
$$
|E_{i+1} - E_i| \leq \Delta_{\text{tol}}
$$
is reached. The value set as 100 times floating-point machine precision `100 * f64::epsilon`.
This conversion is provided by `anomaly_mean_to_eccentric`.

**warning**

Because this is a numerical method, convergence is not guaranteed. There is an upper 
limit of 10 iterations to reach convergence. Since convergence may not occur the output of 
the function is a `Result`, forcing the user to explicitly handle the case where the algorithm 
does not converage.

Since Python lacks Rust's same error handling mechanisms, non-convergence will result in a 
runtime error.


```python
import brahe as bh

bh.initialize_eop()

ecc = 45.0  # Starting eccentric anomaly (degrees)
e = 0.01  # Eccentricity

# Convert to mean anomaly
mean_anomaly = bh.anomaly_eccentric_to_mean(ecc, e, angle_format=bh.AngleFormat.DEGREES)
print(f"Eccentric anomaly: {ecc:.3f} deg")
print(f"Mean anomaly:      {mean_anomaly:.3f} deg")

# Convert back from mean to eccentric anomaly
ecc_2 = bh.anomaly_mean_to_eccentric(
    mean_anomaly, e, angle_format=bh.AngleFormat.DEGREES
)
print(f"Round-trip result: {ecc_2:.3f} deg")

# Verify round-trip accuracy
print(f"Difference:        {abs(ecc - ecc_2):.2e} deg")
```



**Plot Source**

```python
import os
import pathlib
import sys
import plotly.graph_objects as go
import brahe as bh

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from brahe_theme import get_theme_colors, save_themed_html

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))

# Ensure output directory exists
os.makedirs(OUTDIR, exist_ok=True)

# Generate data

# Generate range of eccentric anomalies (degrees)
ecc = [x for x in range(0, 360)]

# Compute mean anomaly for range of eccentricities
eccentricities = [0.0, 0.1, 0.3, 0.5, 0.7, 0.9]
mean_data = {}
for e in eccentricities:
    # Take output mod 360 to wrap from 0 to 360 degrees
    mean_data[e] = [
        bh.anomaly_eccentric_to_mean(x, e, angle_format=bh.AngleFormat.DEGREES) % 360
        for x in ecc
    ]

# Create figure with theme support


def create_figure(theme):
    """Create figure with theme-specific colors."""
    colors = get_theme_colors(theme)

    fig = go.Figure()

    # Color palette for different eccentricities
    color_palette = [
        colors["primary"],
        colors["secondary"],
        colors["accent"],
        colors["error"],
        colors["primary"],
        colors["secondary"],
    ]

    # Add traces for each eccentricity
    for i, e in enumerate(eccentricities):
        fig.add_trace(
            go.Scatter(
                x=ecc,
                y=mean_data[e],
                mode="lines",
                line=dict(color=color_palette[i % len(color_palette)], width=2),
                name=f"e = {e:.1f}",
                showlegend=True,
            )
        )

    # Configure axes
    fig.update_xaxes(
        tickmode="linear",
        tick0=0,
        dtick=30,
        title_text="Eccentric Anomaly (deg)",
        range=[0, 360],
        showgrid=False,
    )

    fig.update_yaxes(
        tickmode="linear",
        tick0=0,
        dtick=30,
        title_text="Mean Anomaly (deg)",
        range=[0, 360],
        showgrid=False,
    )

    return fig


# Generate and save both themed versions
light_path, dark_path = save_themed_html(create_figure, OUTDIR / SCRIPT_NAME)
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")
```

## True and Mean Anomaly Conversions

Methods to convert from true anomaly to mean anomaly are 
provided for convenience. These methods simply wrap successive calls to two 
`anomaly_true_to_mean`. To perform the reverse conversion use
`anomaly_mean_to_true`.


```python
import brahe as bh

bh.initialize_eop()

nu = 45.0  # Starting true anomaly (degrees)
e = 0.01  # Eccentricity

# Convert to mean anomaly
mean_anomaly = bh.anomaly_true_to_mean(nu, e, angle_format=bh.AngleFormat.DEGREES)
print(f"True anomaly:      {nu:.3f} deg")
print(f"Mean anomaly:      {mean_anomaly:.3f} deg")

# Convert back from mean to true anomaly
nu_2 = bh.anomaly_mean_to_true(mean_anomaly, e, angle_format=bh.AngleFormat.DEGREES)
print(f"Round-trip result: {nu_2:.3f} deg")

# Verify round-trip accuracy
print(f"Difference:        {abs(nu - nu_2):.2e} deg")
```



**Plot Source**

```python
import os
import pathlib
import sys
import plotly.graph_objects as go
import brahe as bh

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from brahe_theme import get_theme_colors, save_themed_html

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))

# Ensure output directory exists
os.makedirs(OUTDIR, exist_ok=True)

# Generate data

# Generate range of true anomalies (degrees)
nu = [x for x in range(0, 360)]

# Compute mean anomaly for range of eccentricities
eccentricities = [0.0, 0.1, 0.3, 0.5, 0.7, 0.9]
mean_data = {}
for e in eccentricities:
    # Take output mod 360 to wrap from 0 to 360 degrees
    mean_data[e] = [
        bh.anomaly_true_to_mean(x, e, angle_format=bh.AngleFormat.DEGREES) % 360
        for x in nu
    ]

# Create figure with theme support


def create_figure(theme):
    """Create figure with theme-specific colors."""
    colors = get_theme_colors(theme)

    fig = go.Figure()

    # Color palette for different eccentricities
    color_palette = [
        colors["primary"],
        colors["secondary"],
        colors["accent"],
        colors["error"],
        colors["primary"],
        colors["secondary"],
    ]

    # Add traces for each eccentricity
    for i, e in enumerate(eccentricities):
        fig.add_trace(
            go.Scatter(
                x=nu,
                y=mean_data[e],
                mode="lines",
                line=dict(color=color_palette[i % len(color_palette)], width=2),
                name=f"e = {e:.1f}",
                showlegend=True,
            )
        )

    # Configure axes
    fig.update_xaxes(
        tickmode="linear",
        tick0=0,
        dtick=30,
        title_text="True Anomaly (deg)",
        range=[0, 360],
        showgrid=False,
    )

    fig.update_yaxes(
        tickmode="linear",
        tick0=0,
        dtick=30,
        title_text="Mean Anomaly (deg)",
        range=[0, 360],
        showgrid=False,
    )

    return fig


# Generate and save both themed versions
light_path, dark_path = save_themed_html(create_figure, OUTDIR / SCRIPT_NAME)
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")
```

[^1]: D. Vallado, *Fundamentals of Astrodynamics and Applications (4th Ed.)*, 2010  
[https://celestrak.org/software/vallado-sw.php](https://celestrak.org/software/vallado-sw.php)