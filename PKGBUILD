# Maintainer: Petexy <https://github.com/Petexy>

pkgname=linexin-installer
pkgver=1.3.1.r
pkgrel=1
_currentdate=$(date +"%Y-%m-%d%H-%M-%S")
pkgdesc='Linexin Operating System Installer'
url='https://github.com/Petexy'
arch=(x86_64)
license=('GPL-3.0')
depends=(
  python-gobject
  gtk4
  libadwaita
  python
)
makedepends=(
)

package() {
   mkdir -p ${pkgdir}/usr/share/linexin-installer
   cp -rf ${srcdir}/usr/share/ ${pkgdir}/usr/
}
