"""Generate a reproducible WiX manifest for the complete portable app."""
from pathlib import Path
import hashlib, uuid, xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
NS='http://schemas.microsoft.com/wix/2006/wi'
ET.register_namespace('',NS)
def tag(parent,name,**attrs): return ET.SubElement(parent,'{'+NS+'}'+name,attrs)
def ident(prefix,value): return prefix+hashlib.sha256(value.encode()).hexdigest()[:24]

def main():
    source=ROOT/'dist'/'PrismCompare'
    if not (source/'PrismCompare.exe').is_file():raise SystemExit('Build the app first.')
    out=ROOT/'build'/'installer';out.mkdir(parents=True,exist_ok=True)
    wix=ET.Element('{'+NS+'}Wix')
    product=tag(wix,'Product',Id='*',Name='Prism Compare',Language='2052',Version='0.1.12',Manufacturer='Prism Compare',UpgradeCode='204A554F-844F-4FE3-B938-3BB126C6B874')
    tag(product,'Package',InstallerVersion='500',Compressed='yes',InstallScope='perMachine',Platform='x64',Description='Prism Compare image and document comparison')
    tag(product,'MajorUpgrade',DowngradeErrorMessage='A newer version of Prism Compare is already installed.')
    tag(product,'MediaTemplate',EmbedCab='yes',CompressionLevel='high')
    tag(product,'Property',Id='ARPPRODUCTICON',Value='AppIcon.exe')
    tag(product,'Property',Id='WIXUI_INSTALLDIR',Value='INSTALLFOLDER')
    tag(product,'Icon',Id='AppIcon.exe',SourceFile=str(source/'PrismCompare.exe'))
    condition=tag(product,'Condition',Message='64-bit Windows is required.');condition.text='Installed OR VersionNT64'
    target=tag(product,'Directory',Id='TARGETDIR',Name='SourceDir')
    program=tag(target,'Directory',Id='ProgramFiles64Folder')
    install=tag(program,'Directory',Id='INSTALLFOLDER',Name='Prism Compare')
    menus=tag(target,'Directory',Id='ProgramMenuFolder')
    menu=tag(menus,'Directory',Id='AppMenu',Name='Prism Compare')
    tag(target,'Directory',Id='DesktopFolder')
    feature=tag(product,'Feature',Id='Main',Title='Prism Compare',Level='1',Absent='disallow')
    dirs={Path('.'):install}
    def directory(rel):
        if rel not in dirs:dirs[rel]=tag(directory(rel.parent),'Directory',Id=ident('D',rel.as_posix()),Name=rel.name)
        return dirs[rel]
    for file in sorted(source.rglob('*')):
        if not file.is_file():continue
        rel=file.relative_to(source);name=rel.as_posix();cid=ident('C',name)
        comp=tag(directory(rel.parent),'Component',Id=cid,Guid=str(uuid.uuid5(uuid.NAMESPACE_URL,'prismcompare/file/'+name)).upper(),Win64='yes')
        fid='MainExe' if name=='PrismCompare.exe' else ident('F',name)
        item=tag(comp,'File',Id=fid,Source=str(file),KeyPath='yes')
        if fid=='MainExe':
            for sid,dest in [('StartMenuShortcut','AppMenu'),('DesktopShortcut','DesktopFolder')]:
                tag(item,'Shortcut',Id=sid,Directory=dest,Name='Prism Compare',WorkingDirectory='INSTALLFOLDER',Icon='AppIcon.exe',Advertise='yes')
            tag(comp,'RemoveFolder',Id='RemoveAppMenu',Directory='AppMenu',On='uninstall')
        tag(feature,'ComponentRef',Id=cid)
    shell=tag(install,'Component',Id='ExplorerMenu',Guid='C77C3AE9-C7B4-42CF-ACFA-BE98B315D451',Win64='yes')
    for kind in ['*','Directory']:
        key='Software\\Classes\\'+kind+'\\shell\\PrismCompare'
        tag(shell,'RegistryValue',Root='HKLM',Key=key,Type='string',Value='使用 Prism Compare 比较',KeyPath='yes' if kind=='*' else 'no')
        tag(shell,'RegistryValue',Root='HKLM',Key=key,Name='Icon',Type='string',Value='[INSTALLFOLDER]PrismCompare.exe,0')
        tag(shell,'RegistryValue',Root='HKLM',Key=key,Name='MultiSelectModel',Type='string',Value='Document')
        tag(shell,'RegistryValue',Root='HKLM',Key=key+'\\command',Type='string',Value='"[INSTALLFOLDER]PrismCompare.exe" --shell "%1"')
    tag(feature,'ComponentRef',Id='ExplorerMenu')
    tag(product,'UIRef',Id='WixUI_InstallDir')
    tag(product,'WixVariable',Id='WixUILicenseRtf',Value=str(ROOT/'assets'/'installer_notice.rtf'))
    ET.indent(wix)
    manifest=out/'PrismCompare.wxs';ET.ElementTree(wix).write(manifest,encoding='utf-8',xml_declaration=True)
    print(manifest)
if __name__=='__main__':main()
