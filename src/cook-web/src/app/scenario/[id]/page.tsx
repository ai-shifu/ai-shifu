import ScenarioRoot from '@/components/scenario-root'
export default async function Page({
    params,
}: {
    params: Promise<{ id: string }>
}) {
    const id = (await params).id;
    return (
        <div className='h-screen w-full'>
            <ScenarioRoot id={id} />
        </div>
    )
}
