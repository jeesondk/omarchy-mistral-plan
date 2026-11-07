import QtQuick
import Quickshell
import Quickshell.Io

// No UI of its own. refresh-budget.py saves Mistral's budget as a ready-made
// patch; this keeps it applied to the Vibe record the Agents panel draws, because
// Omarchy's collector rewrites that record without one on every refresh. Disabling
// the plugin undoes it: the next collector run writes a clean record.
Item {
  id: root

  readonly property int refreshMs: 15 * 60 * 1000
  // A failed check at login is usually the network not being up yet.
  readonly property int retryMs: 5 * 60 * 1000
  readonly property string script: Qt.resolvedUrl("refresh-budget.py").toString().replace(/^file:\/\//, "")
  readonly property string stateDir: Quickshell.env("XDG_STATE_HOME") || (Quickshell.env("HOME") + "/.local/state")

  property var patch: null

  function loadPatch(content) {
    try {
      var parsed = JSON.parse(content)
      root.patch = parsed && typeof parsed === "object" ? parsed : null
    } catch (e) {
      root.patch = null
    }
    applyPatch()
  }

  function applyPatch() {
    if (!root.patch) return
    var record
    try {
      record = JSON.parse(recordFile.text())
    } catch (e) {
      return
    }
    // Our own write lands here too, so this is also what ends the loop.
    if (!record || record.id !== "vibe" || record.limitsFetchedAt === root.patch.limitsFetchedAt) return
    var keys = Object.keys(root.patch)
    for (var i = 0; i < keys.length; i++) record[keys[i]] = root.patch[keys[i]]
    recordFile.setText(JSON.stringify(record) + "\n")
  }

  FileView {
    id: patchFile
    path: root.stateDir + "/omarchy/mistral-plan/budget.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.loadPatch(text())
    onLoadFailed: root.patch = null
  }

  FileView {
    id: recordFile
    path: root.stateDir + "/omarchy/agents/usage/vibe.json"
    watchChanges: true
    atomicWrites: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.applyPatch()
  }

  // The collector replaces the record's inode, which can lose a file watch.
  Timer {
    interval: 60 * 1000
    repeat: true
    running: true
    onTriggered: {
      patchFile.reload()
      recordFile.reload()
    }
  }

  Process {
    id: refresh
    command: ["python3", "-I", "-B", root.script]
    stderr: StdioCollector {
      onStreamFinished: if (text.trim() !== "") console.warn(text.trim())
    }
    onExited: (exitCode) => {
      if (exitCode !== 0) console.warn("mistral-plan: refresh exited with", exitCode)
      timer.interval = exitCode === 0 ? root.refreshMs : root.retryMs
      timer.restart()
    }
  }

  Timer {
    id: timer
    interval: root.refreshMs
    onTriggered: refresh.running = true
  }

  Component.onCompleted: refresh.running = true
}
