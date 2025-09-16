document.addEventListener("DOMContentLoaded", () => {
  const root = document.querySelector("#result_list tbody")

  const PK = 0
  const DEPTH = 1
  const CHILDREN = 2
  const TR = 3
  const TOGGLE = 4
  const LOADED = 5

  const nodes = {}
  const parents = []

  const context = JSON.parse(
    document.querySelector("#tree-admin-context").dataset.context,
  )

  // Get the list of parent IDs that have children from the backend
  const parentIdsWithChildren = new Set(context.parentIdsWithChildren || [])
  console.log("Context:", context)
  console.log("Parent IDs with children:", parentIdsWithChildren)

  for (const toggle of root.querySelectorAll(".collapse-toggle")) {
    const node = toggle.closest("tr")
    const pk = +toggle.dataset.pk
    const treeDepth = +toggle.dataset.treeDepth

    console.log("Processing node:", pk, "depth:", treeDepth)

    // Check if this node has children (either visible or lazy-loadable)
    const hasChildren = parentIdsWithChildren.has(pk)
    console.log("Node", pk, "has children:", hasChildren)

    // For lazy loading: if depth >= maxInitialDepth, children are not loaded yet
    const childrenLoaded =
      !context.lazyLoading || treeDepth < context.maxInitialDepth
    console.log("Node", pk, "children loaded:", childrenLoaded)

    const rec = [pk, treeDepth, [], node, toggle, childrenLoaded]
    parents[treeDepth] = rec
    nodes[pk] = rec

    node.dataset.pk = pk
    node.dataset.treeDepth = treeDepth

    // Show toggle if this node has children
    if (hasChildren) {
      toggle.classList.remove("collapse-hide")
      console.log("Showing toggle for node:", pk)

      // Add appropriate CSS class for styling
      if (!childrenLoaded) {
        toggle.classList.add("has-lazy-children")
        console.log("Added has-lazy-children class to node:", pk)
      }
    }

    if (treeDepth > 0) {
      // parent may be on the previous page if the changelist is paginated.
      const parent = parents[treeDepth - 1]
      if (parent) {
        parent[CHILDREN].push(rec)
        console.log("Added node", pk, "as child of", parent[PK])
      }
    }
  }

  console.log("Final nodes object:", nodes)

  function insertRowsFromHTML(htmlString, insertAfter) {
    console.log("insertRowsFromHTML called with:", htmlString, insertAfter)

    // Create a temporary table to properly parse table rows
    const tempTable = document.createElement("table")
    const tempTbody = document.createElement("tbody")
    tempTable.appendChild(tempTbody)
    tempTbody.innerHTML = htmlString

    const newRows = tempTbody.querySelectorAll("tr")
    console.log("Found rows to insert:", newRows.length, Array.from(newRows))

    let currentInsertAfter = insertAfter
    for (const row of newRows) {
      console.log("Inserting row:", row, "after:", currentInsertAfter)
      currentInsertAfter.parentNode.insertBefore(
        row,
        currentInsertAfter.nextSibling,
      )
      currentInsertAfter = row
    }

    return Array.from(newRows)
  }

  function loadChildren(pk) {
    const node = nodes[pk]
    if (!node || node[LOADED]) {
      return Promise.resolve()
    }

    // Add loading indicator
    node[TOGGLE].classList.add("loading")

    return fetch(`load-children/${pk}/`, {
      credentials: "include",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
      },
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }
        return response.json()
      })
      .then((data) => {
        console.log("Received data:", data)

        if (data.error) {
          throw new Error(data.error)
        }

        // Update parent IDs with children if new data was provided
        if (data.parent_ids_with_children) {
          for (const pid of data.parent_ids_with_children) {
            parentIdsWithChildren.add(pid)
          }
        }

        console.log("HTML to insert:", data.html)

        // Insert new rows using the rendered HTML
        const newRows = insertRowsFromHTML(data.html, node[TR])
        console.log("Inserted rows:", newRows)

        // Process each new row to create node records
        for (const newRow of newRows) {
          const childPk = +newRow.dataset.pk
          const childDepth = +newRow.dataset.treeDepth
          const childToggle = newRow.querySelector(".collapse-toggle")

          // Check if this child has children and update toggle accordingly
          const childHasChildren = parentIdsWithChildren.has(childPk)
          if (childHasChildren && childToggle) {
            childToggle.classList.remove("collapse-hide")

            // If child is at depth >= maxInitialDepth, its children are not loaded
            const childrenLoaded = childDepth < context.maxInitialDepth
            if (!childrenLoaded) {
              childToggle.classList.add("has-lazy-children")
            }
          }

          const childRec = [
            childPk,
            childDepth,
            [],
            newRow,
            childToggle,
            childDepth < context.maxInitialDepth,
          ]

          nodes[childPk] = childRec
          node[CHILDREN].push(childRec)
        }

        node[LOADED] = true
        node[TOGGLE].classList.remove("loading")
        return newRows
      })
      .catch((error) => {
        console.error("Failed to load children:", error)
        node[TOGGLE].classList.remove("loading")
        // Could add user notification here
        throw error
      })
  }

  function setCollapsed(pk, collapsed) {
    const node = nodes[pk]
    console.log("setCollapsed called:", pk, collapsed, "node:", node)
    node[TOGGLE].classList.toggle("collapsed", collapsed)

    // If expanding and children not loaded yet, load them
    if (!collapsed && context.lazyLoading && !node[LOADED]) {
      console.log("Loading children for node:", pk)
      loadChildren(pk).then(() => {
        console.log("Children loaded, applying visibility")
        // After loading, apply collapse state to new children
        for (const rec of node[CHILDREN]) {
          rec[TR].classList.toggle("collapse-hide", false)
        }
      })
      return
    }

    console.log(
      "Using existing children for node:",
      pk,
      "children:",
      node[CHILDREN],
    )
    // Normal collapse/expand for already loaded children
    for (const rec of node[CHILDREN]) {
      rec[TR].classList.toggle("collapse-hide", collapsed)
      if (collapsed) {
        setCollapsed(rec[PK], collapsed)
      }
    }
  }

  function initiallyCollapse(minDepth) {
    for (const rec of Object.values(nodes)) {
      const hasChildren = parentIdsWithChildren.has(rec[PK])
      if (rec[DEPTH] >= minDepth && hasChildren) {
        setCollapsed(rec[PK], true)
      }
    }
  }

  root.addEventListener("click", (e) => {
    const collapseToggle = e.target.closest(".collapse-toggle")
    if (collapseToggle) {
      e.preventDefault()
      const pk = +collapseToggle.dataset.pk
      const isCurrentlyCollapsed =
        collapseToggle.classList.contains("collapsed")
      console.log(
        "Toggle clicked:",
        pk,
        "currently collapsed:",
        isCurrentlyCollapsed,
      )
      setCollapsed(pk, !isCurrentlyCollapsed)
    }
  })

  initiallyCollapse(context.initiallyCollapseDepth)
})

document.addEventListener("DOMContentLoaded", () => {
  let statusElement

  const performMove = (formData) => {
    return fetch("move-node/", {
      credentials: "include",
      method: "POST",
      body: formData,
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }
        return response.text()
      })
      .then((result) => {
        if (result === "ok") {
          setMoving({ ..._moving, highlight: true })
          window.location.reload()
        } else {
          throw new Error("Move operation failed")
        }
      })
      .catch((error) => {
        console.error("Move operation failed:", error)
        setMoving(null)
        alert("Failed to move node. Please try again.")
        throw error // Re-throw for additional handling if needed
      })
  }

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
      if (moving.toRoot) {
        statusElement.innerHTML = `
          ${moving.title}
          <button class="confirm-root-move">Confirm</button>
          <button class="cancel-move">Cancel</button>
        `
      } else {
        statusElement.innerHTML = `
          ${moving.title}
          <button class="cancel-move">Cancel</button>
        `
      }
      statusElement.style.display = "block"
      document.body.setAttribute(
        "data-move",
        moving.toRoot ? "root" : "regular",
      )

      document
        .querySelector(`tr[data-pk="${moving.pk}"]`)
        .classList.add("move-selected")
    } else {
      statusElement.style.display = "none"
      document.body.removeAttribute("data-move")
    }
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".move-cut")
    if (btn) {
      if (_moving?.pk === btn.dataset.pk && !_moving?.toRoot) {
        // Same node in regular mode - cancel
        setMoving(null)
      } else {
        // Start or switch to regular move mode
        setMoving({ pk: btn.dataset.pk, title: btn.title })
      }
    }

    const rootBtn = e.target.closest(".move-to-root")
    if (rootBtn) {
      if (_moving?.pk === rootBtn.dataset.pk && _moving?.toRoot) {
        // Same node in root mode - cancel
        setMoving(null)
      } else {
        // Start or switch to root move mode
        setMoving({
          pk: rootBtn.dataset.pk,
          title: rootBtn.title,
          toRoot: true,
        })
      }
    }

    const confirmBtn = e.target.closest(".confirm-root-move")
    if (confirmBtn && _moving?.toRoot) {
      // Execute the root move
      const csrf = document.querySelector(
        "input[name=csrfmiddlewaretoken]",
      ).value
      const body = new FormData()
      body.append("csrfmiddlewaretoken", csrf)
      body.append("move", _moving.pk)
      body.append("position", "root")

      performMove(body)
    }

    const cancelBtn = e.target.closest(".cancel-move")
    if (cancelBtn) {
      setMoving(null)
      return
    }

    const el = e.target.closest(".move-status")
    if (el && !e.target.closest(".confirm-root-move")) {
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

      performMove(body).catch(() => {
        // Reset the select to its default state on error
        select.value = ""
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
