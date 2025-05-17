import ShifuRoot from '@/components/shifu-root'
export default async function Page({
    params,
}: {
    params: Promise<{ id: string }>
}) {
    const id = (await params).id;
    return (
        <div className='h-screen w-full'>
            <ShifuRoot id={id} />
        </div>
    )
}
