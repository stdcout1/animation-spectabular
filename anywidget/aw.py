"""
idea:
  python (model)       ->         esm (view)
       │                              │
  update attrs                  observe changes
  via loops or                  update svg attrs
  formal model                  live
"""

import anywidget
import traitlets
import asyncio
import time


ESM = """
// translated from python
const W = 500, H = 600;
const SHAFT_X = 160, SHAFT_W = 130;
const CABIN_H = 70, CABIN_PAD = 5;
const FLOOR_H = 85;
const BOTTOM_Y = H - 50;
const NUM_FLOORS = 6;

function floorY(floor) {
  return BOTTOM_Y - (floor + 1) * FLOOR_H + (FLOOR_H - CABIN_H) / 2;
}

function createSVG(el) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("width", W);
  svg.setAttribute("height", H);
  svg.style.background = "#e8e4de";
  svg.style.borderRadius = "8px";
  svg.style.border = "1px solid #ccc";

  function make(tag, attrs) {
    const e = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    return e;
  }

  const shaftTop = BOTTOM_Y - NUM_FLOORS * FLOOR_H;

  // facade
  svg.appendChild(make("rect", {
    x: SHAFT_X - 40, y: shaftTop - 20,
    width: SHAFT_W + 80, height: NUM_FLOORS * FLOOR_H + 20,
    fill: "#d4cfc7", stroke: "#999", "stroke-width": 1.5, rx: 3,
  }));

  // shaft
  svg.appendChild(make("rect", {
    x: SHAFT_X, y: shaftTop,
    width: SHAFT_W, height: NUM_FLOORS * FLOOR_H,
    fill: "#2a2a2a", stroke: "#555", "stroke-width": 2,
  }));

  // floor lines + labels + indicator lights
  const floorLights = [];
  for (let f = 0; f < NUM_FLOORS; f++) {
    const fy = BOTTOM_Y - f * FLOOR_H;
    svg.appendChild(make("line", {
      x1: SHAFT_X - 40, y1: fy, x2: SHAFT_X + SHAFT_W + 40, y2: fy,
      stroke: "#888", "stroke-width": 1,
    }));
    const label = make("text", {
      x: SHAFT_X - 25, y: fy - FLOOR_H / 2 + 5,
      fill: "#555", "font-size": 16, "text-anchor": "middle",
      "font-family": "sans-serif",
    });
    label.textContent = f + "F";
    svg.appendChild(label);

    // floor indicator light
    const light = make("circle", {
      cx: SHAFT_X - 10, cy: fy - FLOOR_H / 2,
      r: 4, fill: "#333", stroke: "#555", "stroke-width": 1,
    });
    svg.appendChild(light);
    floorLights.push(light);
  }

  const cabinX = SHAFT_X + CABIN_PAD;
  const cabinW = SHAFT_W - 2 * CABIN_PAD;

  const cabinBody = make("rect", {
    x: cabinX, y: floorY(0), width: cabinW, height: CABIN_H,
    fill: "#b0a898", stroke: "#666", "stroke-width": 2, rx: 3,
  });
  svg.appendChild(cabinBody);

  const cabinInt = make("rect", {
    x: cabinX + 3, y: floorY(0) + 3, width: cabinW - 6, height: CABIN_H - 6,
    fill: "#8a7e70", stroke: "none", rx: 2,
  });
  svg.appendChild(cabinInt);

  const doorW = (cabinW - 12) / 2;
  const doorH = CABIN_H - 10;
  const doorBaseX = cabinX + 5;

  const doorL = make("rect", {
    x: doorBaseX, y: floorY(0) + 5, width: doorW, height: doorH,
    fill: "#9e9588", stroke: "#777", "stroke-width": 1, rx: 1,
  });
  svg.appendChild(doorL);

  const doorR = make("rect", {
    x: doorBaseX + doorW + 2, y: floorY(0) + 5, width: doorW, height: doorH,
    fill: "#9e9588", stroke: "#777", "stroke-width": 1, rx: 1,
  });
  svg.appendChild(doorR);

  const panelX = 370, panelY = 40;
  svg.appendChild(make("rect", {
    x: panelX, y: panelY, width: 90, height: 100,
    fill: "#1a1a1a", stroke: "#555", "stroke-width": 2, rx: 6,
  }));
  const panelLabel = make("text", {
    x: panelX + 45, y: panelY + 18, fill: "#888",
    "font-size": 10, "text-anchor": "middle", "font-family": "sans-serif",
  });
  panelLabel.textContent = "FLOOR";
  svg.appendChild(panelLabel);

  const floorText = make("text", {
    x: panelX + 45, y: panelY + 70, fill: "#00cc66",
    "font-size": 40, "text-anchor": "middle", "font-family": "monospace",
    "font-weight": "bold",
  });
  floorText.textContent = "0";
  svg.appendChild(floorText);

  const statusText = make("text", {
    x: panelX + 45, y: panelY + 92, fill: "#888",
    "font-size": 9, "text-anchor": "middle", "font-family": "sans-serif",
  });
  statusText.textContent = "IDLE";
  svg.appendChild(statusText);

  el.appendChild(svg);

  // return "handles" to the mutable variables.
  // in a preexisting svg, the setup would be slightly diffrent
  // my idea is that we return a handle to ALL attributes of all elemetns.
  // visb crawls though the svg using java's xml packages and does this,
  // i still need to think how to do this in our setting... :(
  return {
    cabinBody, cabinInt, doorL, doorR,
    floorText, statusText, floorLights,
    doorBaseX, doorW
  };
}

export default {
  render({ model, el }) {
    // tutorial call these refs. i guess and ode to javascript libraies.
    const refs = createSVG(el);
    function update() {
      const pos      = model.get("cabin_position");   // float: floor number
      const doorPct  = model.get("door_open_pct");     // 0.0=closed, 1.0=open
      const floorNum = model.get("floor_display");     // int shown on panel
      const status   = model.get("status_text");       // string
      const targetFl = model.get("target_floor");       // int

      // get the values and use them how we want to.
      // just translating the python behvaiour that i made before...
      // we should do this in python, but its easier here.
      // ideally we should be able to setAttributes for all elemetns from the python code
      // but that was very involved for this mock animations (and involved exporting all the attributes...)
      const cabY = floorY(pos);
      refs.cabinBody.setAttribute("y", cabY);
      refs.cabinInt.setAttribute("y", cabY + 3);

      const doorSlide = doorPct * (refs.doorW - 4);
      refs.doorL.setAttribute("x", refs.doorBaseX - doorSlide);
      refs.doorL.setAttribute("y", cabY + 5);
      refs.doorR.setAttribute("x", refs.doorBaseX + refs.doorW + 2 + doorSlide);
      refs.doorR.setAttribute("y", cabY + 5);

      // so much nicer than what i had to do in python...
      refs.floorText.textContent = String(floorNum);
      refs.statusText.textContent = status;

      const nearestFloor = Math.round(pos);
      refs.floorLights.forEach((light, f) => {
        if (f === nearestFloor) {
          light.setAttribute("fill", "#00cc66");
        } else {
          light.setAttribute("fill", "#333");
        }
      });
    }

    // "handler" for all model attributes
    for (const attr of ["cabin_position", "door_open_pct",
                         "floor_display", "status_text", "target_floor"]) {
      model.on("change:" + attr, update);
    }

    update();  // initial render
  }
};
"""



class ElevatorWidget(anywidget.AnyWidget):
    _esm = ESM

    cabin_position = traitlets.Float(0.0).tag(sync=True)
    door_open_pct  = traitlets.Float(1.0).tag(sync=True)
    floor_display  = traitlets.Int(0).tag(sync=True)
    status_text    = traitlets.Unicode("IDLE").tag(sync=True)
    target_floor   = traitlets.Int(0).tag(sync=True)



def _lerp(a, b, t):
    return a + (b - a) * t


async def animate(widget, start_floor=0, end_floor=4, speed=1.0):
    # the hope is that the "animator" (user of the libary) only has to make this...
    # note that this is async, so we can chain animations and use the state in the next call :)
    # animation tutorial call this dt from calculus
    fps = 30
    dt = 1.0 / fps # 30 frames per second.

    # timing constants
    DOOR_TIME  = 0.8
    TRAVEL_PER = 0.6   # time to pass a floor
    DWELL      = 0.5

    n_floors = abs(end_floor - start_floor)
    travel_time = n_floors * TRAVEL_PER
    direction = 1 if end_floor > start_floor else -1

    # these two functions we should provide, and also abstract out the fps.
    # too much work for this mock implementation
    async def wait(seconds):
        await asyncio.sleep(seconds / speed)

    async def tween(setter, start, end, secs):
        # we should prob use a tween library instead 
        # of my barbaric implementation
        # just calls the setter and updates it to the lerped valued
        # we prob need a smoother cuz its kinda choppy. 
        steps = max(1, int(secs / speed * fps))
        for i in range(steps + 1):
            setter(_lerp(start, end, i / steps))
            await wait(dt)

    # animiation code below...
    # init
    widget.cabin_position = float(start_floor)
    widget.door_open_pct = 1.0
    widget.floor_display = start_floor
    widget.target_floor = end_floor
    widget.status_text = "DOORS OPEN"
    await wait(DWELL)

    # close doors
    widget.status_text = "DOORS CLOSING"
    await tween(lambda v: setattr(widget, 'door_open_pct', v),
                1.0, 0.0, DOOR_TIME)

    # traveling
    widget.status_text = f"TRAVELING {'▲' if direction > 0 else '▼'}"

    # caclculate how many intermediate frames there are animate and sleeo for those 
    #frames
    steps = max(1, int(travel_time / speed * fps))
    for i in range(steps + 1):
        pos = _lerp(start_floor, end_floor, i / steps)
        widget.cabin_position = pos
        widget.floor_display = round(pos)
        await asyncio.sleep(dt / speed)

    # open
    widget.cabin_position = float(end_floor)
    widget.floor_display = end_floor
    widget.status_text = "DOORS OPENING"
    await tween(lambda v: setattr(widget, 'door_open_pct', v),
                0.0, 1.0, DOOR_TIME)

    widget.status_text = "ARRIVED"
    await wait(DWELL)
    widget.status_text = "IDLE"