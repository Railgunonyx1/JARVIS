import QtQuick
import QtQuick3D
import QtQuick3D.Helpers
import QtQuick.Controls
import QtQuick.Layouts

View3D {
    id: view3D
    anchors.fill: parent
    environment: SceneEnvironment {
        clearColor: "#0a0e14"
        backgroundMode: SceneEnvironment.Color
        antialiasingMode: SceneEnvironment.MSAA
    }

    PerspectiveCamera {
        id: camera
        position: Qt.vector3d(0, 0, 8)
        eulerRotation: Qt.vector3d(0, 0, 0)
    }

    DirectionalLight {
        id: dirLight
        brightness: 0.8
        eulerRotation: Qt.vector3d(-30, 45, 0)
    }
    
    /* Ambient illumination provided by SceneEnvironment.clearColor and
       DefaultMaterial diffuseColor; no separate light node needed. */
    
    /* Fallback: if a ambient light type is required for older QtQuick3D,
       define as a rectangle panel that contributes ambient color. */
    Rectangle {
        anchors.fill: parent
        visible: false
        color: "#0a0e14"
    }

    Model {
        id: chatPanel
        source: "#Rectangle"
        position: Qt.vector3d(-3, 0.5, 0)
        scale: Qt.vector3d(2.5, 1.8, 1)
        materials: DefaultMaterial {
            diffuseColor: "#1a2332"
            opacity: 0.85
        }
        eulerRotation: Qt.vector3d(0, 15, 0)
    }

    Model {
        id: sysPanel
        source: "#Rectangle"
        position: Qt.vector3d(0, 0.5, -1)
        scale: Qt.vector3d(2.5, 1.8, 1)
        materials: DefaultMaterial {
            diffuseColor: "#1a2332"
            opacity: 0.85
                    }
    }

    Model {
        id: voicePanel
        source: "#Rectangle"
        position: Qt.vector3d(3, 0.5, 0)
        scale: Qt.vector3d(2.5, 1.8, 1)
        materials: DefaultMaterial {
            diffuseColor: "#1a2332"
            opacity: 0.85
                    }
        eulerRotation: Qt.vector3d(0, -15, 0)
    }

    Model {
        id: tasksPanel
        source: "#Rectangle"
        position: Qt.vector3d(0, -1.5, 1)
        scale: Qt.vector3d(2.5, 1.8, 1)
        materials: DefaultMaterial {
            diffuseColor: "#1a2332"
            opacity: 0.85
                    }
    }

    Model {
        id: workspacePanel
        source: "#Rectangle"
        position: Qt.vector3d(-3, -1.5, 0)
        scale: Qt.vector3d(2.5, 1.8, 1)
        materials: DefaultMaterial {
            diffuseColor: "#1a2332"
            opacity: 0.85
                    }
        eulerRotation: Qt.vector3d(0, 15, 0)
    }

    Model {
        id: settingsPanel
        source: "#Rectangle"
        position: Qt.vector3d(3, -1.5, 0)
        scale: Qt.vector3d(2.5, 1.8, 1)
        materials: DefaultMaterial {
            diffuseColor: "#1a2332"
            opacity: 0.85
                    }
        eulerRotation: Qt.vector3d(0, -15, 0)
    }

    MouseArea {
        anchors.fill: parent
        property real lastX: 0
        property real lastY: 0
        onPressed: {
            lastX = mouse.x
            lastY = mouse.y
        }
        onPositionChanged: {
            var dx = mouse.x - lastX
            var dy = mouse.y - lastY
            camera.eulerRotation.y += dx * 0.5
            camera.eulerRotation.x = Math.max(-60, Math.min(60, camera.eulerRotation.x - dy * 0.5))
            lastX = mouse.x
            lastY = mouse.y
        }
        onWheel: {
            camera.position.z = Math.max(3, Math.min(15, camera.position.z - wheel.angleDelta.y * 0.01))
        }
    }
}
