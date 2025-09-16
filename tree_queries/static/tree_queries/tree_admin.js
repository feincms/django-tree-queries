document.addEventListener("DOMContentLoaded", () => {
  const root = document.querySelector("#result_list tbody")

  const PK = 0
  const DEPTH = 1
  const CHILDREN = 2
  const TR = 3
  const TOGGLE = 4

  const nodes = {}
  const parents = []

  for (const toggle of root.querySelectorAll(".collapse-toggle")) {
    const node = toggle.closest("tr")
    const pk = +toggle.dataset.pk
    const treeDepth = +toggle.dataset.treeDepth
    const rec = [pk, treeDepth, [], node, toggle]
    parents[treeDepth] = rec
    nodes[pk] = rec

    node.dataset.pk = pk
    node.dataset.treeDepth = treeDepth

    if (treeDepth > 0) {
      // parent may be on the previous page if the changelist is paginated.
      const parent = parents[treeDepth - 1]
      if (parent) {
        parent[CHILDREN].push(rec)
        parent[TOGGLE].classList.remove("collapse-hide")
      }
    }
  }

  function setCollapsed(pk, collapsed) {
    nodes[pk][TOGGLE].classList.toggle("collapsed", collapsed)
    for (const rec of nodes[pk][CHILDREN]) {
      rec[TR].classList.toggle("collapse-hide", collapsed)
      setCollapsed(rec[PK], collapsed)
    }
  }

  function initiallyCollapse(minDepth) {
    for (const rec of Object.values(nodes)) {
      if (rec[DEPTH] >= minDepth && rec[CHILDREN].length) {
        setCollapsed(rec[PK], true)
      }
    }
  }

  root.addEventListener("click", (e) => {
    const collapseToggle = e.target.closest(".collapse-toggle")
    if (collapseToggle) {
      e.preventDefault()
      setCollapsed(
        +collapseToggle.dataset.pk,
        !collapseToggle.classList.contains("collapsed"),
      )
    }
  })

  const context = JSON.parse(
    document.querySelector("#tree-admin-context").dataset.context,
  )
  initiallyCollapse(context.initiallyCollapseDepth)
})

document.addEventListener("DOMContentLoaded", () => {
  let statusElement

  const showMoving = (moving) => {
    if (!statusElement) {
      statusElement = document.createElement("div")
      statusElement.className = "move-status"
      document.body.append(statusElement)
    }

    for (const el of document.querySelectorAll(".move-selected"))
      el.classList.remove("move-selected")

    if (moving?.highlight) {
      const row = document.querySelector(`tr[data-pk="${moving.pk}"]`)

      row.classList.add("move-highlight")

      setTimeout(() => {
        row.classList.remove("move-highlight")
        setMoving(null)
      }, 1000)
    } else if (moving) {
      statusElement.textContent = `${moving.title} (click here to cancel)`
      statusElement.style.display = "block"
      document.body.classList.add("moving")

      document
        .querySelector(`tr[data-pk="${moving.pk}"]`)
        .classList.add("move-selected")
    } else {
      statusElement.style.display = "none"
      document.body.classList.remove("moving")
    }
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".move-cut")
    if (btn) {
      setMoving(
        _moving?.pk === btn.dataset.pk
          ? null
          : { pk: btn.dataset.pk, title: btn.title },
      )
    }

    const el = e.target.closest(".move-status")
    if (el) {
      setMoving(null)
    }
  })

  document.addEventListener("change", (e) => {
    const select = e.target.closest(".move-paste")
    if (select?.value && _moving) {
      const csrf = document.querySelector(
        "input[name=csrfmiddlewaretoken]",
      ).value
      const body = new FormData()
      body.append("csrfmiddlewaretoken", csrf)
      body.append("move", _moving.pk)
      body.append("relative_to", select.dataset.pk)
      body.append("position", select.value)

      fetch("move-node/", {
        credentials: "include",
        method: "POST",
        body,
      }).then(() => {
        setMoving({ ..._moving, highlight: true })
        window.location.reload()
      })

      // console.debug(JSON.stringify({ _moving, where: `${select.dataset.pk}:${select.value}` }))
    }
  })

  document.body.addEventListener("keyup", (e) => {
    if (e.key === "Escape") setMoving(null)
  })

  const _key = `f3moving:${location.pathname}`
  let _moving
  try {
    _moving = JSON.parse(sessionStorage.getItem(_key))
  } catch (e) {
    console.error(e)
  }

  const setMoving = (moving) => {
    _moving = moving
    if (_moving) {
      sessionStorage.setItem(_key, JSON.stringify(_moving))
    } else {
      sessionStorage.removeItem(_key)
    }
    showMoving(_moving)
  }

  showMoving(_moving)
})
