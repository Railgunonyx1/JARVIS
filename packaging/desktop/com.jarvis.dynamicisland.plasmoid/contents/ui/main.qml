import QtQuick
import org.kde.plasma.core

PlasmaCore.Item {
    id: root

    property bool expanded: false

    MouseArea {
        anchors.fill: parent
        onClicked: plasmoid.expanded = !plasmoid.expanded
    }
}
