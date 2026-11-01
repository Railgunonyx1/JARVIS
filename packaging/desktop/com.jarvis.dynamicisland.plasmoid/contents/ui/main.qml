import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import org.kde.plasma.plasmoid

PlasmoidItem {
    id: root

    preferredRepresentation: compactRepresentation
    compactRepresentation: Item {
        implicitWidth: island.width
        implicitHeight: island.height

        Rectangle {
            id: island
            anchors.centerIn: parent
            width: 196
            height: 42
            radius: 21
            color: "#101114"
            border.color: "#303238"
            border.width: 1

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 13
                anchors.rightMargin: 13
                spacing: 9

                Rectangle {
                    Layout.preferredWidth: 7
                    Layout.preferredHeight: 7
                    radius: 4
                    color: "#e5484d"
                }

                Text {
                    Layout.fillWidth: true
                    text: "JARVIS"
                    color: "#f3f3f4"
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                    font.letterSpacing: 1.4
                }

                Text {
                    text: Qt.formatDateTime(clock.date, "hh:mm")
                    color: "#f3f3f4"
                    font.pixelSize: 12
                    font.weight: Font.Medium
                }
            }

            MouseArea {
                anchors.fill: parent
                onClicked: root.expanded = !root.expanded
                cursorShape: Qt.PointingHandCursor
            }
        }
    }

    fullRepresentation: Item {
        Layout.minimumWidth: 360
        Layout.minimumHeight: 310
        Layout.preferredWidth: 390
        Layout.preferredHeight: 340

        Rectangle {
            anchors.fill: parent
            radius: 24
            color: "#111216"
            border.color: "#303238"
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 20
                spacing: 15

                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        text: "JARVIS"
                        color: "#f4f4f5"
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                        font.letterSpacing: 2
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        text: Qt.formatDateTime(clock.date, "ddd, dd MMM")
                        color: "#9699a2"
                        font.pixelSize: 11
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: "#292b31"
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    Text {
                        text: Qt.formatDateTime(clock.date, "hh:mm")
                        color: "#ffffff"
                        font.pixelSize: 38
                        font.weight: Font.Light
                    }
                    Text {
                        text: "Desktop control centre"
                        color: "#a2a4ad"
                        font.pixelSize: 12
                    }
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    rowSpacing: 9
                    columnSpacing: 9

                    Repeater {
                        model: [
                            { title: "DISPLAY", detail: "Brightness controls", glyph: "◐" },
                            { title: "AUDIO", detail: "Sound controls", glyph: "◖" },
                            { title: "CONNECTIVITY", detail: "Network and Bluetooth", glyph: "⌁" },
                            { title: "ACTIVITY", detail: "Notifications and tasks", glyph: "◷" }
                        ]

                        delegate: Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 72
                            radius: 13
                            color: "#1b1d22"
                            border.color: "#2c2f36"
                            border.width: 1

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 11
                                spacing: 4
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text {
                                        text: modelData.glyph
                                        color: "#e5484d"
                                        font.pixelSize: 16
                                    }
                                    Item { Layout.fillWidth: true }
                                    Text {
                                        text: modelData.title
                                        color: "#a8aab2"
                                        font.pixelSize: 9
                                        font.weight: Font.DemiBold
                                        font.letterSpacing: 0.8
                                    }
                                }
                                Text {
                                    text: modelData.detail
                                    color: "#f0f0f1"
                                    font.pixelSize: 11
                                }
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                Text {
                    Layout.fillWidth: true
                    text: "Visual foundation · KDE Plasma 6"
                    color: "#666a74"
                    font.pixelSize: 9
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
    }

    Timer {
        id: clock
        interval: 1000
        running: true
        repeat: true
        property date date: new Date()
        onTriggered: date = new Date()
    }
}
